#AdvertAPI-RealtyMX-Lambda  
AWS Lambda to repost NakedApartments ads syndicated from RealtyMX real estate IDX platform.
Called by AWS API gateway via POST request.

##Input  
Lambda takes JSON object `event`

Schema:  
``` python 
event = {
    'username':'STRING',
    'password':'STRING',
    'ads':['STRING', ...]
	}
```
`username` is the NakedApartments login email address  
`password` is the NakedApartments login password  
`ads` is a list of NakedApartment ad webID strings  

###Note  
####This tool will only work with ads that are syndicated from RealtyMX to NakedApartments, and ads previously reposted via this tool. You can tell from `_cR_` being present in the ad webID  
`TIME_LAG` is a global that represents the amount of time (in minutes) that is needed between successful AWS Lambda calls before AWS Lambda will begin to repost ads  
`HOPPER_SIZE` is a global that represents the maximum allowable length of the `ads` list to be reposted  

  