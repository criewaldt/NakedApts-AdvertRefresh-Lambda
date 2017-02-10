#advertapi
from bs4 import BeautifulSoup
import json
import requests
import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError
import datetime
import sys
import uuid
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
import smtplib
import time
from requests_toolbelt import MultipartEncoder

DEBUG = False


#globals
TIME_LAG = 30
HOPPER_SIZE = 50

def check_post_response(response):
    # Checks response from ad post, return code and status message
    #   possible outcomes are:
    # 1) True: Successful post
    # 2) False: Failed: Missing info
    # 3) False: Failed: Already Featured
    # 4) False: Failed: other
    soup = BeautifulSoup(response.text, "html.parser")
    if DEBUG == True:
        dName = 'check post response'
        with open('{}.html'.format(dName), 'w') as w:
            w.write(response.text)
        dName = ''

    #1 - check for success and return True with status
    status = soup.find("div", {"class": "success alert alert-success"})
    if status:
        return (True, 'ok')

    #2 - if no success, check for error and return False with status
    status = soup.find("div", {"class": "alert alert-error"})
    if status:
        error_items = status.find_all("li")
        error_list = []
        for error in error_items:
            error_list.append(error.text)
            print error_list
            return (False, " ".join(error for error in error_list))
    else:
        print 'unknown error'
        return (False, 'unknown error')
                

class AdvertAPI(object):

    def __init__(self, user, forceAuth="false"):
        self.status = self.Validate(user, forceAuth)

    def UpdateActivity(self, ads, status_list):
        #Get the service resource.
        resource = boto3.resource('dynamodb',
            aws_access_key_id='AKIAIOZC3MKUZ2CG6VJQ',
            aws_secret_access_key='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',
            region_name='us-east-1')
        #get activity table object
        activity_table = resource.Table('advertapi-activity')
        #update dynamodb with user activity
        response = activity_table.put_item(
           Item={
                'datetime': str(datetime.datetime.utcnow()),
                'ads': ads,
                'status': status_list,
            }
        )

    def Validate(self, user, forceAuth):
        #Get the service resource.
        resource = boto3.resource('dynamodb',
            aws_access_key_id='AKIAIOZC3MKUZ2CG6VJQ',
            aws_secret_access_key='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',
            region_name='us-east-1')
        client = boto3.client('dynamodb',
            aws_access_key_id='AKIAIOZC3MKUZ2CG6VJQ',
            aws_secret_access_key='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',
            region_name='us-east-1')
        #get user table object
        table = resource.Table('advertapi-users')
        
        #replace '@' character
        user_email = user
        user = user.replace('@', '.....')
        self.user = user
        #do dynamodb request
        response = table.scan(
            FilterExpression=Attr('username').eq(user.lower())
        )
        count = response['Count']
        #if username record found
        if count >= 1:
            timestamp = datetime.datetime.strptime(response['Items'][0]['lastrun'], "%Y-%m-%d %H:%M:%S.%f")
            now = datetime.datetime.utcnow()
            target_time = timestamp + datetime.timedelta(minutes=TIME_LAG)
            
            #force auth
            if forceAuth == "true":
                self.host = response['Items'][0]['host']
                self.naked_string = response['Items'][0]['naked_string']
                print "AdvertAPI has been authorized by force."
                return True
            #is valid?
            if now > target_time:
                #AdvertAPI Validated!
                self.host = response['Items'][0]['host']
                self.naked_string = response['Items'][0]['naked_string']
                response = table.put_item(
                   Item={
                        'username': user,
                        'lastrun': str(datetime.datetime.utcnow()),
                        'host': self.host,
                        'naked_string': self.naked_string,
                    }
                )  
                print "AdvertAPI has been authorized."
                return True
            else:
                lambda_time_email(user_email, (target_time - datetime.timedelta(hours=5)))
                print "You may only use this tool every {} minutes.".format(TIME_LAG)
                return False
        else:
            print "No AdvertAPI user found."
            return False

class NakedApts(object):
    def __init__(self, username, password):
        self.session = requests.Session()
        self.session.headers={'User-Agent' : 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/53.0.2785.143 Safari/537.36'}
        self.status = self.Login(username, password)
        if self.status:
            url = "https://www.nakedapartments.com/broker/listings?all=true&listings_scope=published&order=desc&page=1"
            r = self.session.get(url)
            soup = BeautifulSoup(r.content, "html.parser")
            
            if DEBUG == True:
                dName = 'parse all ads'
                with open('{}.html'.format(dName), 'w') as w:
                    w.write(r.content)
                dName = ''
                    
            tds = soup.find_all("td", {"class":"listing"})
            self.links = {}
            for td in tds:
                webid = td.span.text.split("Web ID: ")[1]
                link =  "https://www.nakedapartments.com"+td.a['href']
                self.links[webid] = link
            

    #LOGIN
    def Login(self, username, password):
        r = self.session.get("https://www.nakedapartments.com/login")
        soup = BeautifulSoup(r.content, "html.parser")
        _csrf = soup.find("meta", {"name":"csrf-token"})
        csrf = _csrf.get('content')
        login_data = {'user_session[email]' : username,
                      'user_session[password]' : password,
                      'authenticity_token' : csrf,
                      'user_session[remember_me]' : 0,
                      'button' : ''}
        
        r = self.session.post('https://www.nakedapartments.com/user_session', data=login_data)
        soup = BeautifulSoup(r.content, "html.parser")

        if DEBUG == True:
            dName = 'login'
            with open('{}.html'.format(dName), 'w') as w:
                w.write(r.content)
            dName = ''
    
        error = soup.find("div", {"class": "error alert alert-error"})
        if error:
            if error.text == "Sorry, your email and password didn't match.":
                print(error.text)
                return False
        else:
            return True
    #LOGOUT
    def Logout(self,):
        r = self.session.get('https://www.nakedapartments.com/logoff')        
        
    def PopulatePayload(self, webid):
        
        url = self.links[webid]
        r = self.session.get(url)
        ad = r.content

        if DEBUG == True:
            dName = 'populate payload'
            with open('{}.html'.format(dName), 'w') as w:
                w.write(ad)
            dName = ''
        
        soup = BeautifulSoup(ad, 'html.parser')
        ad_data = {}

        #radios
        radios = soup.find_all("input", type="radio")
        for radio in radios:
            if radio.get('checked') == 'checked':
                #assign data
                ad_data[radio.get('name')] = radio.get('value')
                
            
        #checkboxes
        checkboxes = soup.find_all("input", type="checkbox")
        amenities = []
        for check in checkboxes:
            if check.get('checked') == 'checked':
                if check.get('name') == "listing[amenity_ids][]":
                    amenities.append(check.get('value'))
                else:
                    #assign data
                    ad_data[check.get('name')] = check.get('value')
        #assign data
        ad_data['listing[amenity_ids][]'] = amenities

        #textbox
        textboxes = soup.find_all("input", type="text")
        for text in textboxes:
            if text.get('checked') != '':
                ad_data[text.get('name')] = text.get('value')

        #textarea - description
        d_textarea = soup.find("textarea", id="listing_description")
        test = d_textarea.prettify(formatter="html")
        test = test.replace("<br>", "<br />")
        test = test.replace('''<textarea class="text" cols="80" id="listing_description" name="listing[description]" rows="10">''',"")
        test = test.replace("</textarea>","")
        test = test.replace("\n","")
        description = test.replace("</br>","")
        #assign data
        ad_data['listing[description]'] = description

        #option
        option = soup.find_all('option', {'selected':'selected'})
        for opt in option:
            if opt.text == 'Manhattan':
                borough = opt.get('value')
            elif opt.text == 'Brooklyn':
                borough = opt.get('value')
            elif opt.text == 'Bronx':
                borough = opt.get('value')
            elif opt.text == 'Staten Island':
                borough = opt.get('value')
            elif opt.text == 'Queens':
                borough = opt.get('value')
            else:
                neighborhood = opt.get('value')
        #assign value
        ad_data['listing[neighborhood_id]'] = neighborhood
        ad_data['listing[borough_id]'] = borough

        #print json.dumps(ad_data, indent=4, sort_keys=True)
        return ad_data

    def Inactivate(self, webid):
        ad_id = self.links[webid].split("/")[5]
        r = self.session.get("https://www.nakedapartments.com/broker/listings")
        soup = BeautifulSoup(r.content, "html.parser")
        _csrf = soup.find("meta", {"name":"csrf-token"})
        csrf = _csrf.get('content')
        payload = {'a':'deactivate',
                   'listings[]':[ad_id],
                   'authenticity_token' : csrf}
        r = self.session.post('https://www.nakedapartments.com/broker/listings/update_listings', data=payload)
        if DEBUG == True:
            dName = 'Inactivate'
            with open('{}.html'.format(dName), 'w') as w:
                w.write(r.content)
            dName = ''

    def CreateID(self,):
        r = self.session.get('https://www.nakedapartments.com/broker/listings/new')
        soup = BeautifulSoup(r.content, "html.parser")
        idd = soup.find("input", {"id": "listing_unique_id"})
        listing_id = idd['value']
        return listing_id

    def UploadImages(self, imgs, ad_id):
        r = self.session.get("https://www.nakedapartments.com/broker/listings/new?id={}".format(ad_id))
        soup = BeautifulSoup(r.content, "html.parser")
        _csrf = soup.find("meta", {"name":"csrf-token"})
        csrf = _csrf.get('content')
        counter = 0
        for img in imgs:
            multipart_data = MultipartEncoder(
            fields = (
                ('authenticity_token', csrf),
                ('listing_image[listing_id]', ad_id),
                ('listing_image[primary]', '0'),
                ('listing_image[floor_plan]', 'false'),
                ('listing_image[images][]', (str(counter), img, 'image/jpeg')),
                ))
        
            _headers = {"Content-Type": multipart_data.content_type,
                        'Host': 'www.nakedapartments.com',
                        'Origin': 'https://www.nakedapartments.com',
                        'Referer': 'https://www.nakedapartments.com/broker/listings/new?id={}'.format(ad_id)}
            response = self.session.post("https://www.nakedapartments.com/broker/listings/images/upload", data=multipart_data, headers=_headers)
            if DEBUG == True:
                dName = str(counter)
                with open('{}.html'.format(dName), 'w') as w:
                    w.write(response.content)
                dName = ''
            counter += 1
            

    def Post(self, payload, imgs):
        
        
        ad_id = self.CreateID()
        refer_url = 'https://www.nakedapartments.com/broker/listings/new?id={}'.format(ad_id)
        r = self.session.get(refer_url)
        soup = BeautifulSoup(r.content, "html.parser")
        _csrf = soup.find("meta", {"name":"csrf-token"})
        csrf = _csrf.get('content')
        payload['Referer'] = refer_url
        payload['listing[unique_id]'] = payload['listing[unique_id]'].split("_cR_")[0]+"_cR_{}".format(str(uuid.uuid4().get_hex().upper()[0:16])[:4])
        payload['action_type'] = 'publish'
        payload['record_state'] = 'new'
        payload['authenticity_token'] = csrf
        data_url = ('https://www.nakedapartments.com/broker/listings/'+ad_id+'/'+'save')

        print '--> Uploading images for:', payload['listing[unique_id]']
        self.UploadImages(imgs, ad_id)

        response = self.session.post(data_url, data=payload)

        if DEBUG == True:
            dName = 'Post'
            with open('{}.html'.format(dName), 'w') as w:
                w.write(response.content)
            dName = ''
            
        #do something with the response
        status = check_post_response(response)
        if status[0]:
            print 'Successfully posted:', payload['listing[unique_id]']
            pub_url = "https://www.nakedapartments.com/rental/{}".format(ad_id)
            edit_url = "https://www.nakedapartments.com/broker/listings/{}/edit".format(ad_id)
            nakedid = payload['listing[unique_id]']
            return (True, {'msg':'ok',
                           'public_url':pub_url,
                     'edit_url':edit_url,
                     'nakedid':nakedid})
        return (False, {'msg':status[1]})
            
    
class RealtyMX(object):
    def __init__(self, host, naked_string):
        self.host = host
        self.naked_string = naked_string
        self.session = requests.Session()
        self.session.headers={'User-Agent' : 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/53.0.2785.143 Safari/537.36'}

    def get_page_id(self, web_id):
        if "_cR_" in web_id:
            web_id = web_id.split("_cR_")[0]
        return web_id.strip(self.naked_string)
    
    def Img_Links(self, web_id):
        page_id = self.get_page_id(web_id)
        url = """http://{}.realtymx.com//admin2/views/dspImage.cfm?id={}""".format(self.host, page_id)
        r = self.session.get(url)
        soup = BeautifulSoup(r.content, 'html.parser')
        results = soup.find_all("img")
        images = [result.get('src') for result in results]
        return images

    def Img_Objects(self, url_list):
        imgs = []
        for url in url_list:
            response = self.session.get(url)
            if response.status_code == 200:
                img = response.content
                imgs.append(img)
        return imgs
    
def lambda_start_email(username, id_list):
    fromaddr = "AdvertAPIbot@gmail.com"
    toaddr = username
    msg = MIMEMultipart()
    msg['From'] = fromaddr
    msg['To'] = username
    #msg['cc'] = 'criewaldt@gmail.com'
    msg['Subject'] = "AdvertAPI-NakedApts: Reposting Has Started"

    body = """Hello,\n\nI will now attempt to repost the following NakedApartment webID's:\n\n"""
    counter = 1
    for _id in id_list:
        body += """{}\n""".format(_id)
    body += "\n"
    body += "Do not make any changes to those ads on your NakedApartments account or I will not be able to repost them.\n\nBeep-boop.\n\n-AdvertAPI Bot"
    body += "\n\nThis email was sent at: {}.\n\n".format(datetime.datetime.utcnow() - datetime.timedelta(hours=5))

    msg.attach(MIMEText(body, 'plain'))
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.ehlo()
    server.starttls()
    server.login(fromaddr, "tulqshqdakaooszh")
    text = msg.as_string()
    server.sendmail(fromaddr, toaddr, text)
    server.quit()

def lambda_status_email(status_list, username):
    fromaddr = "AdvertAPIbot@gmail.com"
    toaddr = username
    msg = MIMEMultipart()
    msg['From'] = fromaddr
    msg['To'] = username
    #msg['cc'] = 'criewaldt@gmail.com'
    msg['Subject'] = "AdvertAPI-NakedApts: Repost Update"

    body = """Hello,\n\nI have an update about your AdvertAPI-NakedApartments repost attempt:\n\n"""
    counter = 1
    for result in status_list:
        if result[0]:
            body += """{n}) Status: Success\nThis is the public link: {p}
This is the edit link: {e}\nThis is the new webID: {w}\n\n""".format(n=str(counter),
                               m=result[1]['msg'], \
                               p=result[1]['public_url'],\
                               e=result[1]['edit_url'], \
                               w=result[1]['nakedid'])
        else:
            body += """{n}) Status: Fail\nMessage: {m}\n\n""".format(n=str(counter), m=result[1]['msg'])
        counter += 1
        
    body += "Beep-boop.\n\n-AdvertAPI Bot"
    body += "\n\nThis email was sent at: {}.\n\n".format(datetime.datetime.utcnow() - datetime.timedelta(hours=5))


    msg.attach(MIMEText(body, 'plain'))
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.ehlo()
    server.starttls()
    server.login(fromaddr, "tulqshqdakaooszh")
    text = msg.as_string()
    server.sendmail(fromaddr, toaddr, text)
    server.quit()

def lambda_time_email(username, target_time):
    fromaddr = "AdvertAPIbot@gmail.com"
    toaddr = username
    msg = MIMEMultipart()
    msg['From'] = fromaddr
    msg['To'] = username
    #msg['cc'] = 'criewaldt@gmail.com'
    msg['Subject'] = "AdvertAPI-NakedApts: Oops!"

    body = """Hello,\n
I cannot repost the ads you wanted because I'm only allowed to run once every {td} minutes, with a maximum of {h} ads per attempt.
\nI'll be ready again at: {tt} EST.\n\n""".format(td=TIME_LAG, h=HOPPER_SIZE, tt=target_time)
    body += "Beep-boop.\n\n-AdvertAPI Bot"
    body += "\n\nThis email was sent at: {}.\n\n".format(datetime.datetime.utcnow() - datetime.timedelta(hours=5))


    msg.attach(MIMEText(body, 'plain'))
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.ehlo()
    server.starttls()
    server.login(fromaddr, "tulqshqdakaooszh")
    text = msg.as_string()
    server.sendmail(fromaddr, toaddr, text)
    server.quit()

def main(event, context):
    username = event['username']
    password = event['password']
    ads = event['ads'][:HOPPER_SIZE]
    now_ads = ads[:5]
    later_ads = ads[5:]
    
    try:
        status_list = event['status_list']
    except KeyError:
        status_list = []
    try:
        forceAuth = event['forceAuth']
    except KeyError:
        forceAuth = 'false'

    try:
        firststart = event['firststart']
    except KeyError:
        lambda_start_email(username, ads)
    
    a = AdvertAPI(username, forceAuth)
    if not a.status:
        print "AdvertAPI has NOT been validated."
        sys.exit()

    na = NakedApts(username, password)
    if not na.status:
        print "NakedApts has NOT been validated."
        sys.exit()

    rx = RealtyMX(a.host, a.naked_string)

    print 'Making ads now!'
    for webid in now_ads:
        try:
            if webid.startswith(a.naked_string):
                #get img objects
                imgs = rx.Img_Objects(rx.Img_Links(webid))
                
                #get ad payload
                payload = na.PopulatePayload(webid)
                
                #inactivate naked ad
                na.Inactivate(webid)

                #repost naked ad
                result = na.Post(payload, imgs)
                status_list.append(result)
            else:
                print "Cannot repost {w} as the webID does not begin with {n}".format(w=webid, n=a.naked_string)
                status_list.append((False, {'msg':'I cannot repost {w} as the webID does not begin with: {n}'.format(w=webid, n=a.naked_string)}))
            
        except KeyError as e:
            print "Couldn't find this webid:", e
            status_list.append((False, {'msg':'''Couldn't find this webid: '''+str(e)}))
        
        #except Exception as e:
        #    print "ERROR: {}".format(e)
        #    status_list.append((False, "{}".format(e)))
        
        #take a nap
        time.sleep(15)

    #refire lambda with leftovers
    if len(later_ads) > 0:
        rPayload = {'ads':later_ads,
                    'username':username,
                    'password':password,
                    'forceAuth':'true',
                    'status_list':status_list,
                    'firststart':'false'
                    }
        lamb = boto3.client('lambda',
            aws_access_key_id='AKIAIOZC3MKUZ2CG6VJQ',
            aws_secret_access_key='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',
            region_name='us-east-1')
        response = lamb.invoke(
            FunctionName='AdvertAPI_RealtyMX',
            InvocationType='Event',
            Payload=json.dumps(rPayload))
        
        print 'Calling myself again with', len(later_ads), 'more ads'
    else:
        print 'Final lambda iteration: Sending status email'
        lambda_status_email(status_list, username)
        
    print 'Done posting ads'
    na.Logout()

    print 'Lambda shutting down...'
    return None
    
if __name__ == "__main__":
    #
    #TEST EVENT
    #
    pass
    """
    event = {'username':'aziff@nylivingsolutions.com',
        'password':'teamziff1976',
        'forceAuth':'true',
        'ads':["asdasd", "NKA_NYLS_13755_cR_2977", "11731384", "NKA_NYLS_13756_cR_1761"]}
    context = ""
    
    main(event, context)
    """


    

    
