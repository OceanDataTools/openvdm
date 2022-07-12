#!/usr/bin/bash

# This script exports the openvdm database to stdout. Use redirect to save the
# output to file.
#
# This script does not export the contents of the messages
# table.    
#
# This script assumes the name of the OpenVDM database is "openvdm"
#

mysqldump openvdm -p --ignore-table=openvdm.OVDM_Messages
mysqldump openvdm -p --no-data OVDM_Messages