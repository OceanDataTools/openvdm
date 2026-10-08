-- Migration: OpenVDM 2.16 -> 2.17
--
-- Add the cruise description (#367). CoreVars values were tinytext (255
-- bytes), too short for a description, so the column becomes text. Safe to
-- run more than once: the row is only added if it's missing.

ALTER TABLE `OVDM_CoreVars` MODIFY `value` text;

INSERT INTO `OVDM_CoreVars` (`name`, `value`)
SELECT 'cruiseDescription', ''
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `OVDM_CoreVars` WHERE `name` = 'cruiseDescription');
