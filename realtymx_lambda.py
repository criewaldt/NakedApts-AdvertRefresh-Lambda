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

def check_post_response(response):
    # Checks response from ad post, return code and status message
    #   possible outcomes are:
    # 1) True: Successful post
    # 2) False: Failed: Missing info
    # 3) False: Failed: Already Featured
    # 4) False: Failed: other
    
    soup = BeautifulSoup(response.text, "html.parser")

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

    def __init__(self, user):
        self.status = self.Validate(user)

    def Validate(self, user):
        #Set TIME_LAG interval (in minutes)
        TIME_LAG = 15
        
        #Get the service resource.
        resource = boto3.resource('dynamodb',
            aws_access_key_id='AKIAIOZC3MKUZ2CG6VJQ',
            aws_secret_access_key='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',
            region_name='us-east-1')
        client = boto3.client('dynamodb',
            aws_access_key_id='AKIAIOZC3MKUZ2CG6VJQ',
            aws_secret_access_key='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',
            region_name='us-east-1')
        #get table object
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
        #if record found return true
        if count >= 1:
            timestamp = datetime.datetime.strptime(response['Items'][0]['lastrun'], "%Y-%m-%d %H:%M:%S.%f")
            now = datetime.datetime.utcnow()
            target_time = timestamp + datetime.timedelta(minutes=TIME_LAG)
            if now > target_time:
                #AdvertAPI Validated!
                self.host = response['Items'][0]['host']
                self.naked_string = response['Items'][0]['naked_string']
                
                #update dynamodb with lambda start time
                
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
                lambda_time_email(user_email, target_time)
                print "You may only use this tool every {} minutes, you last used this tool at {} UTC time.".format(TIME_LAG, response['Items'][0]['lastrun'])
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
            url = "http://www.nakedapartments.com/broker/listings?all=true&listings_scope=published&order=desc&page=1"
            r = self.session.get(url)
            soup = BeautifulSoup(r.content, "html.parser")
            tds = soup.find_all("td", {"class":"listing"})
            self.links = {}
            for td in tds:
                webid = td.span.text.strip("Web ID: ")
                link =  "http://www.nakedapartments.com"+td.a['href']
                self.links[webid] = link

    #LOGIN
    def Login(self, username, password):
        login_data = {'user_session[email]' : username,
                  'user_session[password]' : password,
                  'Referer' : 'https://www.nakedapartments.com/login'
                  }
        
        r = self.session.post('https://www.nakedapartments.com/user_session', data=login_data)
        soup = BeautifulSoup(r.content, "html.parser")
        error = soup.find("div", {"class": "error alert alert-error"})
        if error:
            if error.text == "Sorry, your email and password didn't match.":
                print(error.text)
                return False
        else:
            return True
    #LOGOUT
    def Logout(self,):
        r = self.session.get('http://www.nakedapartments.com/logoff')        
        
    def PopulatePayload(self, webid):
        
        url = self.links[webid]
        r = self.session.get(url)
        ad = r.content
        
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
        payload = {'a':'deactivate',
                   'listings[]':[ad_id]}
        r = self.session.post('http://www.nakedapartments.com/broker/listings/update_listings', data=payload)

    def CreateID(self,):
        r = self.session.get('http://www.nakedapartments.com/broker/listings/new')
        soup = BeautifulSoup(r.content, "html.parser")
        idd = soup.find("input", {"id": "listing_unique_id"})
        listing_id = idd['value']
        return listing_id

    def UploadImages(self, imgs, ad_id):
        for img in imgs:
            fileImages = {'listing_image':img}
            img_url = ('http://www.nakedapartments.com/broker/listings/'+ad_id+'/images/upload_single/0')            
            response = self.session.post(img_url, files=fileImages)

    def Post(self, payload, imgs):

        ad_id = self.CreateID()
        refer_url = 'http://www.nakedapartments.com/broker/listings/new?id={}'.format(ad_id)
        payload['Referer'] = refer_url
        payload['listing[unique_id]'] = payload['listing[unique_id]'].split("_cR_")[0]+"_cR_{}".format(str(uuid.uuid4().get_hex().upper()[0:16])[:3])
        payload['action_type'] = 'publish'
        payload['record_state'] = 'new'
        data_url = ('http://www.nakedapartments.com/broker/listings/'+ad_id+'/'+'save')

        print '--> Uploading images for:', payload['listing[unique_id]']
        self.UploadImages(imgs, ad_id)

        response = self.session.post(data_url, data=payload)        
        #do something with the response
        status = check_post_response(response)
        if status[0]:
            print 'Successfully posted:', payload['listing[unique_id]']
            pub_url = "http://www.nakedapartments.com/rental/{}".format(ad_id)
            edit_url = "http://www.nakedapartments.com/broker/listings/{}/edit".format(ad_id)
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

def lambda_status_email(status_list, username):
    fromaddr = "criewaldt@gmail.com"
    toaddr = username
    msg = MIMEMultipart()
    msg['From'] = fromaddr
    msg['To'] = username
    msg['cc'] = 'criewaldt@gmail.com'
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
            body += """{n}) Status: Fail\nMessage: {m}\n\n""".format(n=str(counter), m=result[1])
        counter += 1
    body += "Beep-boop.\n\n-AdvertAPI Bot"

    msg.attach(MIMEText(body, 'plain'))
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.ehlo()
    server.starttls()
    server.login(fromaddr, "xeqfbqexormtqzrs")
    text = msg.as_string()
    server.sendmail(fromaddr, toaddr, text)
    server.quit()

def lambda_time_email(username, target_time):
    fromaddr = "criewaldt@gmail.com"
    toaddr = username
    msg = MIMEMultipart()
    msg['From'] = fromaddr
    msg['To'] = username
    msg['cc'] = 'criewaldt@gmail.com'
    msg['Subject'] = "AdvertAPI-NakedApts: Oops!"

    body = """Hello,\n
I cannot repost the ads you wanted because I'm only allowed to run once every 15 minutes.
\nI'll be ready again at: {} UTC time.\n\n""".format(target_time)
    
    body += "Beep-boop.\n\n-AdvertAPI Bot"

    msg.attach(MIMEText(body, 'plain'))
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.ehlo()
    server.starttls()
    server.login(fromaddr, "xeqfbqexormtqzrs")
    text = msg.as_string()
    server.sendmail(fromaddr, toaddr, text)
    server.quit()

def main(event, context):
    username = event['username']
    password = event['password']
    ads = event['ads'][:5]
    
    a = AdvertAPI(username)
    if not a.status:
        print "AdvertAPI has NOT been validated."
        sys.exit()

    na = NakedApts(username, password)
    if not na.status:
        print "NakedApts has NOT been validated."
        sys.exit()

    rx = RealtyMX(a.host, a.naked_string)

    print 'Making ads now!'
    status_list = []
    for webid in ads:
        try:
            #get img objects
            imgs = rx.Img_Objects(rx.Img_Links(webid))
            
            #get ad payload
            payload = na.PopulatePayload(webid)
            
            #inactivate naked ad
            na.Inactivate(webid)

            #repost naked ad
            result = na.Post(payload, imgs)
            status_list.append(result)
            
        except KeyError as e:
            print "Couldn't find this webid:", e
            status_list.append((False, '''Couldn't find this webid: '''+str(e)))
        
    print 'Done posting ads'
    na.Logout()

    print 'Sending email'
    lambda_status_email(status_list, username)

    print 'Lambda shutting down...'
    sys.exit()
    
if __name__ == "__main__":
    #
    #TEST EVENT
    #
    event = {'username':'aziff@nylivingsolutions.com',
        'password':'teamziff1976',
        'ads':["NKA_NYLS_11474"]}
    context = ""
    main(event, context)
    #
    #
    #
    


    

    
