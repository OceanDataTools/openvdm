-- Migration: OpenVDM 2.15 -> 2.16
--
-- Add FTP Server as a collection system transfer (#17) and cruise data
-- transfer (#199) type.

INSERT INTO `OVDM_TransferTypes` (`transferTypeID`, `transferType`)
VALUES (5, 'FTP Server')
ON DUPLICATE KEY UPDATE `transferType` = VALUES(`transferType`);

ALTER TABLE `OVDM_CollectionSystemTransfers`
  ADD COLUMN `ftpServer` tinytext AFTER `sshPass`,
  ADD COLUMN `ftpUser` tinytext AFTER `ftpServer`,
  ADD COLUMN `ftpPass` tinytext AFTER `ftpUser`;

ALTER TABLE `OVDM_CruiseDataTransfers`
  ADD COLUMN `ftpServer` tinytext AFTER `sshPass`,
  ADD COLUMN `ftpUser` tinytext AFTER `ftpServer`,
  ADD COLUMN `ftpPass` tinytext AFTER `ftpUser`;

-- Point the DashboardData ship-to-shore transfer at Dashboard_Data (#263).
-- Fresh 2.15 installs seeded it with From_PublicData's ID. The IDs differ
-- between installs, so both directories are looked up by name, and only a
-- row that points at From_PublicData is changed.
UPDATE `OVDM_ShipToShoreTransfers` s
JOIN `OVDM_ExtraDirectories` pub ON pub.`extraDirectoryID` = s.`extraDirectory`
  AND pub.`name` = 'From_PublicData'
JOIN `OVDM_ExtraDirectories` dash ON dash.`name` = 'Dashboard_Data'
SET s.`extraDirectory` = dash.`extraDirectoryID`
WHERE s.`name` = 'DashboardData';
