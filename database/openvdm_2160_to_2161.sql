-- Migration: OpenVDM 2.16.0 -> 2.16.1
--
-- Remove trailing slashes from legacy destination directories. The UI already
-- normalizes new saves, but old values produce unmatched exclusions such as
-- 'Vehicles/Empress//**' when the transfer appends '/**'.
-- Preserve root/all-slash paths, empty strings and NULL. Safe to rerun.
-- Back up the database first; restart affected transfers to rebuild filters.

START TRANSACTION;

UPDATE `OVDM_CollectionSystemTransfers`
SET `destDir` = TRIM(TRAILING '/' FROM `destDir`)
WHERE RIGHT(`destDir`, 1) = '/'
  AND CHAR_LENGTH(TRIM(TRAILING '/' FROM `destDir`)) > 0;

UPDATE `OVDM_ExtraDirectories`
SET `destDir` = TRIM(TRAILING '/' FROM `destDir`)
WHERE RIGHT(`destDir`, 1) = '/'
  AND CHAR_LENGTH(TRIM(TRAILING '/' FROM `destDir`)) > 0;

COMMIT;
