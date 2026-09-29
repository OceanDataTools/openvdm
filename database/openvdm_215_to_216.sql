-- Migration: OpenVDM 2.15 -> 2.16
--
-- Add FTP Server as a collection system transfer type (#17). The type is
-- shared with cruise data transfers, whose form hides it until FTP
-- destinations are supported (#199).

INSERT INTO `OVDM_TransferTypes` (`transferTypeID`, `transferType`)
VALUES (5, 'FTP Server')
ON DUPLICATE KEY UPDATE `transferType` = VALUES(`transferType`);

ALTER TABLE `OVDM_CollectionSystemTransfers`
  ADD COLUMN `ftpServer` tinytext AFTER `sshPass`,
  ADD COLUMN `ftpUser` tinytext AFTER `ftpServer`,
  ADD COLUMN `ftpPass` tinytext AFTER `ftpUser`;
