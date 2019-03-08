# qcheck_hard
Checks quotas on a Qumulo, creates a CSV of pertinent values, and sends nag emails if the quota reaches a certain percentage full. 

Configure in the qconfig.json file with Qumulo credentials, etc. Note that if the shares are not Everyone readable at the top level, you must use the admin username.

Note that multipel Qumulo clusters can be checked with the same script, just set up separate .json files and use -c to set which config file to use. 
