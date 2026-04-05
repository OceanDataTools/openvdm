-- Migration: OpenVDM 2.14 -> 2.15
--
-- Transfer logs are no longer stored in the cruise data directory.
-- They are now written to the path defined by TRANSFER_LOG_DIR in Config.php
-- (default: /var/log/openvdm) and purged after 12 hours (unchanged).

DELETE FROM `OVDM_ExtraDirectories` WHERE `name` = 'Transfer_Logs';
