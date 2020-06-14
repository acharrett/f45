#!/usr/bin/env python3

import boto3
import urllib.request, urllib.error, urllib.parse
import re
from time import sleep
from datetime import datetime, timedelta
from pprint import pprint
from sys import exit
import MySQLdb
import os
import imaplib
import sys
import yaml

def main():
    config_file = 'f45.yaml'

    with open(config_file) as f:
        f45_config = yaml.safe_load(f)

    imap = imaplib.IMAP4_SSL(f45_config['imap']['server'])
    imap.login(f45_config['imap']['username'],f45_config['imap']['password'])
    imap.select(f45_config['imap']['reports_folder'])

    cur,db = db_connect(f45_config)
    table_name=f45_config['db']['table']

    tmp, mailbox_data = imap.search(None, 'ALL')
#    pprint(mailbox_data)
    for msg_uid in mailbox_data[0].split():
        print('mail ' + str(msg_uid))
        tmp, mail = imap.fetch(msg_uid, '(RFC822)')

        image_url = get_workout_from_email(mail)
        print(image_url)
        workout_exists = does_workout_exist_in_db(cur,table_name,image_url)

        if workout_exists is False: 
            workout_info = process_image(image_url,f45_config)
            add_workout_to_db(cur,db,table_name,workout_info)
        else:
          # move the mail to the f45done folder
            print('move ' + str(msg_uid))
#            result = imap.uid('COPY', msg_uid, 'f45done')
            result = imap.copy(msg_uid,f45_config['imap']['done_folder'])
            pprint(result)
            if result[0] == 'OK':
#                mov, data = imap.uid('STORE', msg_uid , '+FLAGS', '(\Deleted)')
                imap.store(msg_uid, '+FLAGS', '\\Deleted')
                imap.expunge()

#            sys.exit(0)

    imap.close()

def process_image(image_url,f45_config):
    f45_bucket = image_url.split("/")[2].split(".")[0]
    print("bucket is " + f45_bucket)
    workout_image = re.sub('^.*amazonaws.com/','',image_url)
    print("image is " + workout_image)
#    print(f45_bucket)
#    print(workout_image)
    s3 = boto3.client('s3')
    s3_resource = boto3.resource('s3')

    if f45_bucket != 'ramen-files':
        region_name = 'eu-west-1'
        my_image_name = 'f45.png'
        f45_bucket = f45_config['aws']['bucket']
        filedata = urllib.request.urlopen(image_url)
        datatowrite = filedata.read()
        with open(my_image_name, 'wb') as f:
            f.write(datatowrite)

        with open(my_image_name, "rb") as f:
            s3.upload_fileobj(f, f45_bucket, my_image_name)
            object_acl = s3_resource.ObjectAcl(f45_bucket, my_image_name)
            response = object_acl.put(ACL='public-read')

        workout_image = my_image_name
    else:
        region_name = 'us-east-1'

    print("Processing in " + region_name)
    textract = boto3.client('textract',region_name=region_name)
    resp = textract.start_document_text_detection(DocumentLocation={'S3Object': {'Bucket': f45_bucket,'Name': workout_image}})

    print(("Job ID is " + resp['JobId']))

    response = {}
    response['JobStatus'] = 'IN_PROGRESS'

    while response['JobStatus'] == 'IN_PROGRESS':
        response = textract.get_document_text_detection(JobId=resp['JobId'])
        print("Sleeping...")
        sleep(10)

    #response = textract.get_document_text_detection(JobId='048b467b21b8b3d952b9e58ee84883d3dfa6e0dffe956afb1f7373f4602c37ed')
    response = textract.get_document_text_detection(JobId=resp['JobId'])

    ocr_text = []
    ct = 0
    for block in response['Blocks']:
        if 'Text' in list(block.keys()):
            ocr_text.append(block['Text'])
            print((str(ct) + " " + block['Text']))
            ct += 1

#    workout_time = datetime.strptime(ocr_text[3],"%I:%M%p - %a %d %b %Y")
#
    #pprint(workout_time)

    workout_info = {}
    workout_date = find_date(ocr_text)
    workout_info['name'] = find_workout_name(ocr_text)
    workout_info['type'] = 'Workout'
    workout_info['time'] = workout_date
    workout_info['day_of_week'] = workout_date.strftime('%A')
    workout_info['calories'] = find_calories(ocr_text)
    workout_info['points'] = find_points(ocr_text)
    workout_info['average_heartrate'] = find_heartrate(ocr_text)
    workout_info['elapsed_mins'] = find_mins(ocr_text)
    workout_info['image_url'] = image_url
    workout_info['weight_band'] = '1'


    pprint(workout_info)
    return workout_info

def find_mins(ocr_text):
    ct=0
    mins=0
    for txt in ocr_text:
        if txt == 'Mins':
           mins=int(ocr_text[ct - 1])
        ct += 1
    return mins

def find_date(ocr_text):
    days = [ 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun' ]
    months = [ 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec' ]
    date = ""
    for txt in ocr_text:
        if any(x in txt for x in days) and any(x in txt for x in months):
            date = txt
            date_format = "%I:%M%p - %a %d %b %Y"
    print("DATE1 " + date)
    time_needs_adjusting = False

    if date == "":
        ct=0
        for txt in ocr_text:
            if (txt.endswith("AM") or txt.endswith("PM")) and ":" in txt:
               if '/' in txt:
                   time_needs_adjusting = True
                   date = txt
                   if '-' in txt:
                       date_format = "%m/%d/%Y - %I:%M:%S %p"
                   else:
                       date_format = "%m/%d/%Y %I:%M:%S %p"
               else:
                   date = txt
                   date += " "
                   date += ocr_text[ct + 1]
                   date += " "
                   date += ocr_text[ct + 2]
                   date += " "
                   date += ocr_text[ct + 3]
                   date += " "
                   date += ocr_text[ct + 4]
                   date += " "
                   date += ocr_text[ct + 5]
                   date_format = "%I:%M%p - %a %d %b %Y"
            elif ("AM -" in txt) or ("PM -" in txt):
                   date = txt
                   date_format = "%I:%M%p - %a %d %b %Y"

            print("DATE " + date + " " + date_format)
            ct += 1

    workout_time = datetime.strptime(date, date_format)

#    if time_needs_adjusting is True:
#        workout_time = workout_time - timedelta(hours=8)


    return workout_time

def find_heartrate(ocr_text):
    heartrate=0
    for txt in ocr_text:
        if txt.startswith('AVE') and txt.endswith('BPM'):
            print(txt)
            heartrate=txt.split(" ")[1]
        elif re.match('[0-9][0-9][0-9]BPM',txt):
            heartrate=txt.rstrip('BPM')

    if heartrate == 0:
        ct=0
        for txt in ocr_text:
            if txt == "BPM":
                print("HR1 " + txt)
                print("HR2 " + ocr_text[ct])
                print("HR3 " + ocr_text[ct - 1])
                heartrate = ocr_text[ct - 1].split(" ")[-1].rstrip('B')
 
            ct += 1

    return heartrate

def find_calories(ocr_text):
    calories="0"
    ct=0

    for txt in ocr_text:
        if calories == "0":
            if re.match('[0-9]+[Cc]al?$',txt):
                calories = txt.rstrip('Ca').rstrip('Cal').rstrip('cal')
            elif txt == 'Cal' and ocr_text[ct - 1] == 'AVE':
                calories = ocr_text[ct - 2]
            elif txt == 'Cal':
                calories = ocr_text[ct - 1]

        ct += 1

    return calories 

def find_points(ocr_text):
    points=0

    for txt in ocr_text:
        if re.match('[0-9][0-9]\.[0-9][ ]?[a-zA-Z]*$',txt):
           print("POINTS " + txt)
           points = txt.rstrip('pts').rstrip('p').rstrip('F')

    return points 

def find_workout_name(ocr_text):
    workout_name = ""

    for txt in ocr_text:
        if workout_name == "":
            if re.match('^([0-9] )?[A-Z][a-z]+?',txt) or txt == 'MVP' or txt == '22' or txt == 'T10':
                workout_name = txt
                if workout_name == 'Wists':
                    workout_name = 'Mkatz'

    workout_name = workout_name.replace('circuit','Circuit')

    return workout_name

def get_workout_from_email(email_contents):
    image_url="unknown"
    email_str = ""
    for chunk in email_contents:
         email_str += str(chunk)

#    email_fh=open(email_file,'r')
#    email_contents=email_fh.read()
#    print email_contents
    email_parts=email_str.split('"')

    opener = urllib.request.build_opener(NoRedirect)

    for email_part in email_parts:
        if 'charturl' in email_part or 'f45graphs' in email_part:
            charturl=email_part.replace('=\\r\\n','')
            print(charturl)

            if 'charturl' in charturl:   
                response=opener.open(charturl)
                if response.code == 302:
                    image_url = response.headers['Location']
            else:
                image_url = charturl

    return image_url

def db_connect(f45_config):
    try:
        db = MySQLdb.connect(host=f45_config['db']['host'],
                            user=f45_config['db']['user'],
                            passwd=f45_config['db']['password'],
                            db=f45_config['db']['dbname'])

    except MySQLdb.Error as e:
        print("Error %d: %s" % (e.args[0], e.args[1]))

    cur = db.cursor()
    return cur,db

def does_workout_exist_in_db(cur,table_name,image_url):
    exists = False
    select_sql="SELECT id FROM " + table_name + " WHERE image_url='" + image_url + "'"
    try:
        cur.execute(select_sql)
    except Exception as e:
        print(repr(e))

    for (id) in cur:
        exists = True

    return exists

def add_workout_to_db(cur,db,table_name,workout_info):
    insert_sql='INSERT into ' + table_name + ' (date_time,day_of_week,calories,points,workout_name,elapsed_seconds,average_heartrate,weight_band,image_url) VALUES ('
    insert_sql += "'" + workout_info['time'].strftime("%Y-%m-%d %H:%M:%S") + "',"
    insert_sql += "'" + workout_info['day_of_week'] + "',"
    insert_sql += "'" + workout_info['calories'] + "',"
    insert_sql += "'" + workout_info['points'] + "',"
    insert_sql += "'" + workout_info['name'] + "',"
    insert_sql += "'" + str(int(workout_info['elapsed_mins'])*60) + "',"
    insert_sql += "'" + workout_info['average_heartrate'] + "',"
    insert_sql += "'" + workout_info['weight_band'] + "',"
    insert_sql += "'" + workout_info['image_url'] + "')"

    print(insert_sql)

    try:
        cur.execute(insert_sql)
    except Exception as e:
        print(repr(e))
        print(insert_sql)
    db.commit()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

main()
