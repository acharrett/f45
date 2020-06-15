#!/usr/bin/python3

import MySQLdb
from datetime import datetime, timedelta
import time
from pprint import pprint
import statistics
import smtplib
from email.mime.text import MIMEText
from argparse import ArgumentParser
import yaml

def main():
    config_file = 'f45.yaml'

    with open(config_file) as f:
        f45_config = yaml.safe_load(f)

    cur, db = db_connect(f45_config)
    week_ago = datetime.now() - timedelta(days=7)
    sql_week_ago = week_ago.strftime('%Y-%m-%d %H:%M:%S')
    sql_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    sql_select = "SELECT id,points,elapsed_seconds,workout_name FROM f45_workouts WHERE date_time BETWEEN '" + sql_week_ago + "' AND '" + sql_now + "' AND workout_name != 'Calypso Kings'"
    data_to_send = False
    just_print = True

    parser = ArgumentParser()

    parser.add_argument("-s", "--send", help="send the email", default=False, action='store_true')
    f45args = parser.parse_args()

    if f45args.send is True:
        just_print = False

    stats = {}
    by_workout_name = {}

    for workout_time in ['45', '60']:
        stats[workout_time] = {}
        stats[workout_time]['workouts'] = []

    try:
        cur.execute(sql_select)
    except Exception as e:
        print(repr(e))

    for (id, points, elapsed_seconds, workout_name) in cur:
        if elapsed_seconds == 2700:
            workout_time = '45'
        else:
            workout_time = '60'

        stats[workout_time]['workouts'].append(points)
#        print(str(id) + " " + str(points) + " " + str(elapsed_seconds))

        if workout_name not in by_workout_name.keys():
            by_workout_name[workout_name] = []

        by_workout_name[workout_name].append(points)

#    pprint(stats)

    message = "Summary of the last 7 days\n\n"

    for workout_time in ['45', '60']:
        workout_count = len(stats[workout_time]['workouts'])

        if workout_count > 0:
            avg = round(statistics.mean(stats[workout_time]['workouts']), 1)
            message += "Average of " + workout_time + " min workouts, over " + str(workout_count) + " workouts: " + str(avg) + "\n\n"
            data_to_send = True
        else:
            message += "No " + workout_time + " min workouts in the time period\n\n"

    for workout_name in by_workout_name.keys():
        workout_count = len(by_workout_name[workout_name])
        avg = round(statistics.mean(by_workout_name[workout_name]), 1)
        message += "Average of " + workout_name + " workouts, over " + str(workout_count) + " workouts: " + str(avg) + "\n\n"

    if data_to_send is True:
        message += "Calypso Kings workouts excluded from statistics\n\n"
        if just_print is False:
            sender_address = f45_config['report']['sender_email']
            email_rcpt = f45_config['report']['recipient_email']

            msg = MIMEText(message)
            msg['Subject'] = 'F45 7 day summary'
            msg['From'] = f45_config['report']['sender_name'] + ' <' + sender_address + '>'
            msg['To'] = f45_config['report']['recipient_name'] + ' <' + email_rcpt + '>'
#            print(message)
            smtp_server = smtplib.SMTP(f45_config['report']['smtp_server'])
#            smtp_server.set_debuglevel(1)
            smtp_server.sendmail(sender_address, [email_rcpt], msg.as_string())
            smtp_server.quit()
        else:
            print(message)

def db_connect(f45_config):
    try:
        db = MySQLdb.connect(host=f45_config['db']['host'],
                             user=f45_config['db']['user'],
                             passwd=f45_config['db']['password'],
                             db=f45_config['db']['dbname'])

    except MySQLdb.Error as e:
        print("Error %d: %s" % (e.args[0], e.args[1]))

    cur = db.cursor()
    return cur, db


main()
