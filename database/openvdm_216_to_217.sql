-- Migration: OpenVDM 2.16 -> 2.17
--
-- Add the cruise description (#367) and the bounding boxes of the cruise
-- and the current lowering, cruiseExtent (#366) and loweringExtent (#399).
-- CoreVars values were tinytext (255 bytes), too short for a description, so
-- the column becomes text. Add a description to collection system transfers
-- and extra directories (#432), and the Rebuild Cruise README (#431) and
-- Rebuild Lowering README (#445) tasks.
-- Safe to run more than once: rows and columns are only added if they're
-- missing.

ALTER TABLE `OVDM_CoreVars` MODIFY `value` text;

INSERT INTO `OVDM_CoreVars` (`name`, `value`)
SELECT 'cruiseDescription', ''
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `OVDM_CoreVars` WHERE `name` = 'cruiseDescription');

INSERT INTO `OVDM_CoreVars` (`name`, `value`)
SELECT 'cruiseExtent', ''
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `OVDM_CoreVars` WHERE `name` = 'cruiseExtent');

INSERT INTO `OVDM_CoreVars` (`name`, `value`)
SELECT 'loweringExtent', ''
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `OVDM_CoreVars` WHERE `name` = 'loweringExtent');

-- Collection system transfer and extra directory descriptions (#432).
-- MySQL has no ADD COLUMN IF NOT EXISTS, so each column is only added when
-- information_schema doesn't list it yet ("DO 0" does nothing and prints
-- nothing).
SET @add_column = (SELECT IF(COUNT(*) = 0,
  'ALTER TABLE `OVDM_CollectionSystemTransfers` ADD COLUMN `description` text AFTER `longName`',
  'DO 0')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'OVDM_CollectionSystemTransfers'
    AND COLUMN_NAME = 'description');
PREPARE add_column FROM @add_column;
EXECUTE add_column;
DEALLOCATE PREPARE add_column;

SET @add_column = (SELECT IF(COUNT(*) = 0,
  'ALTER TABLE `OVDM_ExtraDirectories` ADD COLUMN `description` text AFTER `longName`',
  'DO 0')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'OVDM_ExtraDirectories'
    AND COLUMN_NAME = 'description');
PREPARE add_column FROM @add_column;
EXECUTE add_column;
DEALLOCATE PREPARE add_column;

-- Describe the required extra directories, as new installs do, in the shape
-- of the extra directory description template (#449). Descriptions written by
-- hand are kept; the earlier 2.17 wording (#432) is replaced.
UPDATE `OVDM_ExtraDirectories`
SET `description` = CONCAT('Contents: the files OpenVDM''s Data Dashboard is built from: the data and quality test results its plugins extract from the collection systems'' raw files, and the manifest that lists them. Written by OpenVDM.', CHAR(10), 'Files: JSON (.json): one for each processed raw file, and the manifest.', CHAR(10), 'Sub-directories: the same folders as the raw files in the cruise directory. Each lowering''s files and manifest are under its lowering''s folder.')
WHERE `name` = 'Dashboard_Data' AND `required` = 1
  AND (`description` IS NULL OR `description` = ''
       OR `description` = 'The files the Data Dashboard is built from: the data and quality test results OpenVDM''s plugins extract from the raw files (JSON), and the manifest that lists them.');

UPDATE `OVDM_ExtraDirectories`
SET `description` = CONCAT('Contents: files from the ship''s PublicData share, where scientists and crew share files during the cruise, copied here when the cruise is finalized.', CHAR(10), 'Files: any type, as saved on the share.', CHAR(10), 'Sub-directories: as on the PublicData share.')
WHERE `name` = 'From_PublicData' AND `required` = 1
  AND (`description` IS NULL OR `description` = ''
       OR `description` = 'Files from the ship''s PublicData share, where scientists and crew share files during the cruise. They''re copied here when the cruise is finalized.');

-- The Rebuild Cruise README maintenance task (#431)
INSERT INTO `OVDM_Tasks` (`name`, `longName`, `cruiseOrLowering`, `status`, `enable`, `pid`)
SELECT 'rebuildCruiseReadme', 'Rebuild the {cruise_name} README', 0, 2, 1, 0
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `OVDM_Tasks` WHERE `name` = 'rebuildCruiseReadme');

-- The Rebuild Lowering README maintenance task (#445)
INSERT INTO `OVDM_Tasks` (`name`, `longName`, `cruiseOrLowering`, `status`, `enable`, `pid`)
SELECT 'rebuildLoweringReadme', 'Rebuild the {lowering_name} README', 1, 2, 1, 0
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `OVDM_Tasks` WHERE `name` = 'rebuildLoweringReadme');
