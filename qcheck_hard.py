#!/usr/bin/env python
import os
import sys
import json
import smtplib
import argparse
from email.mime.text import MIMEText
from qumulo.rest_client import RestClient


# Size Definitions
KILOBYTE = 1024
MEGABYTE = 1024 * KILOBYTE
GIGABYTE = 1024 * MEGABYTE
TERABYTE = 1024 * GIGABYTE



# Import qconfig.json for login information and other settings
def getconfig(configpath):
    configdict = {}
    try:
        with open (configpath, 'r') as j:
            config = json.load(j)
    
        configdict['sender'] = str(config['email settings']['sender_address'])
        configdict['smtp_server'] = str(config['email settings']['server'])
        configdict['host'] = str(config['qcluster']['url'])
        configdict['user'] = str(config['qcluster']['user'])
        configdict['password'] = str(config['qcluster']['password'])
        configdict['port'] = 8000
        configdict['storagename'] = str(config['qcluster']['name'])
        configdict['header'] = 'Lab,SpaceUsed,TotalSpace,TotalFile'
        configdict['logfile'] = str(config['output_log']['logfile'])
        quota_recip = {}
    
        for quota in config['quotas']:
            quota = str(quota)
            quota_recip[quota] = {}
            quota_recip[quota]['recipients'] = (config['quotas'][quota]['mail_to'])
            quota_recip[quota]['warn_percent'] = int(config['quotas'][quota]['warn_percent'])
    
    except Exception, excpt:
        print "Improperly formatted {} or missing file: {}".format(configpath, excpt)
        sys.exit(1)

    return configdict, quota_recip

def login(configdict):
    '''Obtain credentials from the REST server'''
    try:
        rc = RestClient(configdict['host'], configdict['port'])
        rc.login(configdict['user'], configdict['password'])
    except Exception, excpt:
        print "Error connecting to the REST server: %s" % excpt
        print __doc__
        sys.exit(1)
    return rc

def send_mail(configdict, recipients, subject, body):
    try:
        mmsg = MIMEText(body, 'html')
        mmsg['Subject'] = subject
        mmsg['From'] = configdict['sender']
        mmsg['To'] = ", ".join(recipients)

        session = smtplib.SMTP(configdict['smtp_server'])
        session.sendmail(configdict['sender'], recipients, mmsg.as_string())
        session.quit()
    except Exception,excpt:
        print excpt

def build_mail(nfspath, quotaname, current_usage, quota, configdict, quota_recip, emailtype):
    try:
        sane_current_usage = float(current_usage) / float(TERABYTE)
        sane_quota = quota / TERABYTE
        body = ""
        if 'special' in quotaname and emailtype == 'warn':
            labname = quotaname.replace("special-","").capitalize()
            subject = 'Special Data Storage Warning'
            body += 'Dear User,<br><br>'
            body += 'This is a courtesy warning that your lab ({}) has reached greater than {}% ({:.2f} TB/{} TB) '\
                    'of its currently allocated storage limit for special data. '\
            body += 'Failure to remedy this situation before 98% of your storage quota is reached will prevent all future processing of '\
                    'data. We hope this warning will provide you with enough time to prevent any down time. '\
                    'If you have any questions or concerns, please contact us at: blah@example.com<br><br>'
            body += 'Regards,<br><br>Storageadmins<br>'
            print "built warn"
        elif 'special' in quotaname and emailtype == 'full':
            labname = quotaname.replace("special-","").capitalize()
            subject = '!!!Special Data Storage Alert!!!'
            body += 'Dear User,<br><br>'
            body += 'Your lab ({}) has reached its currently allocated storage limit of {} TB for special data. '\
                    'In order to continue to process your data, we need you to perform one of the '\
                    'following remedial actions. <br><br>'.format(labname, sane_quota) 
            body += '1. Remove some of your older data that is no longer needed.<br><br>'
            body += '2. Please submit a helpdesk ticket '\
                    'to have your storage quota increased.<br><br>'
            body += 'Failure to remedy this situation is preventing all future processing for your lab. '\
                    'If you have any questions or concerns, '\
                    'please contact us at: blah@example.com<br><br>'
            body += 'Regards,<br><br>Storageadmins<br>'
        elif emailtype == 'warn':
            subject = quotaname + " Quota Near Limit"
            body += "The usage on {} has reached {}% of the quota.<br>".format(nfspath, quota_recip['warn_percent'])
            body += "Current usage: %0.2f TB<br>" %sane_current_usage
            body += "Quota: %0.2f TB<br>" %sane_quota
            body += "<br>"
        elif emailtype == 'full':   
            subject = quotaname + " Quota Exceeded" 
            body += "The usage on {} has been exceeded. No further writes are allowed.<br>".format(nfspath)
            body += "Current usage: %0.2f TB<br>" %sane_current_usage
            body += "Quota: %0.2f TB<br>" %sane_quota
            body += "<br>"
        send_mail(configdict, quota_recip['recipients'], subject, body)
    except Exception, excpt:
        print "Something went wrong: " + excpt

def free_space(rc):
    fs_stats = rc.fs.read_fs_stats()
    freesize = fs_stats['free_size_bytes']
    totalsize = fs_stats['total_size_bytes']
    return str(freesize), str(totalsize)

def get_all_quotas(rc):
    try:
        quotalist = []
        all_quotas_raw = rc.quota.get_all_quotas_with_status()
        #print list(all_quotas_raw)
        #quotalist = list(all_quotas_raw)[0]['quotas']
        for l in list(all_quotas_raw):
            quotalist.extend(l['quotas'])
        #print(quotalist)

    except Exception, excpt:
        print "An error occurred contacting the storage for the quota list: {}".format(excpt)
        sys.exit(1)

    return quotalist

def process_quotas(rc,configdict,quota_recip,quotalist):
    lablist = []
    for quota in quotalist:
        toppath = str(quota['path'])
        fs_stats = rc.fs.read_dir_aggregates(toppath)
        total_files = int(fs_stats['total_files'])
        usage = int(quota['capacity_usage'])
        hquota = int(quota['limit'])
        if 'special' in toppath:
            lab = os.path.relpath(toppath,'/special/groups')
            special = 'special'
            nfspath = os.path.join('/sgroups', lab)
            quotaname = 'special-' + lab
        elif 'nobackup' in toppath:
            lab = os.path.relpath(toppath,'/nobackup')
            nfspath = os.path.join('/nobackup', lab)
            special = ''
            quotaname = lab
        elif 'nearline' in toppath:
            lab = os.path.relpath(toppath,'/nearline')
            nfspath = os.path.join('/nearline', lab)
            special = ''
            quotaname = lab

        lablist.append([lab,usage,hquota,total_files,special])
        percentage = 100 * usage / hquota
        try:
            if percentage >= 98 and special == 'special':
                checkfile = os.path.join('/dev/shm', quotaname + 'full')
                emailtype = 'full'
            elif percentage >= quota_recip[quotaname]['warn_percent'] and percentage < 100:
                emailtype = 'warn'
                checkfile = os.path.join('/dev/shm', quotaname + 'warn')
            elif percentage >= 100:
                checkfile = os.path.join('/dev/shm', quotaname + 'full')
                emailtype = 'full'
            if not os.path.isfile(checkfile):
                with open(checkfile,"a+") as f:
                    pass
                try:
                    build_mail(nfspath, quotaname, usage, hquota, configdict, quota_recip[quotaname],emailtype)
                except Exception, excpt:
                    excpt
        except:
            continue 
    lablist.sort()
    return lablist

def main(argv):
    ### Edit the configpath for the location of your qconfig.json ### 
    configpath = "/root/bin/nrs_quota/qconfig.json"
    #################################################################

    parser = argparse.ArgumentParser('Check quota status, create log file, and email if over quota')
    parser.add_argument('-c', '--config', type=str, default=configpath, required=False)
    args = parser.parse_args()
    configpath = args.config

    configdict, reciplist = getconfig(configpath)
    rc = login(configdict)
    freesize, totalsize = free_space(rc)
    quotalist = get_all_quotas(rc)
    lablist = process_quotas(rc,configdict,reciplist,quotalist)

    # Overwrite log file with new data
    with open(configdict['logfile'], "w") as file:
        file.write(configdict['header'] + '\n')
        file.write("FREE,{},{}\n".format(freesize, totalsize))
        for line in lablist:
            file.write("{0}\n".format(", ".join(str(i) for i in line)))

# Main
if __name__ == '__main__':
    main(sys.argv[1:])
