Directory contains scripts used to install/update OpenVDM, and helper scripts:

- `install-openvdm.sh`: installs or updates OpenVDM.
- `export_openvdm_db.sh`: exports the OpenVDM database.
- `sample_ftp_server.py`: local FTP server for the sample data's FTP transfers.
- `update_md5_summary.py`: queues an MD5 summary update for files a hook or script wrote into the cruise directory, e.g. `/opt/openvdm/venv/bin/python /opt/openvdm/utils/update_md5_summary.py Products/CTD_QA/report.pdf`. Python scripts can call `OpenVDM.update_md5_summary()` instead.
