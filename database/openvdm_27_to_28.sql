LOCK TABLES `OVDM_CoreVars` WRITE;
/*!40000 ALTER TABLE `OVDM_CoreVars` DISABLE KEYS */;

INSERT INTO `OVDM_CoreVars` (`coreVarID`, `name`, `value`)
VALUES
  (20,'cruiseConfigFn','ovdm_config.json'),
  (21,'loweringConfigFn','lowering_config.json'),
  (22,'md5SummaryFn','md5_summary.txt'),
  (23,'md5SummaryMd5Fn','md5_summary.md5'),
  (24,'dataDashboardManifestFn','manifest.json');

/*!40000 ALTER TABLE `OVDM_CoreVars` ENABLE KEYS */;
UNLOCK TABLES;

# Add columnes to table OVDM_CollectionSystemTransfers
# ------------------------------------------------------------

LOCK TABLES `OVDM_CollectionSystemTransfers` WRITE;
/*!40000 ALTER TABLE `OVDM_CollectionSystemTransfers` DISABLE KEYS */;
ALTER TABLE `OVDM_CollectionSystemTransfers`
ADD `skipEmptyDirs` int(1) unsigned NOT NULL DEFAULT '1',
ADD `skipEmptyFiles` int(1) unsigned NOT NULL DEFAULT '1',
ADD `syncFromSource` int(1) unsigned NOT NULL DEFAULT '0';

/*!40000 ALTER TABLE `OVDM_CollectionSystemTransfers` ENABLE KEYS */;
UNLOCK TABLES;

# Add columnes to table OVDM_CruiseDataTransfers
# ------------------------------------------------------------

LOCK TABLES `OVDM_CruiseDataTransfers` WRITE;
/*!40000 ALTER TABLE `OVDM_CruiseDataTransfers` DISABLE KEYS */;
ALTER TABLE `OVDM_CruiseDataTransfers`
ADD `skipEmptyDirs` int(1) unsigned NOT NULL DEFAULT '1',
ADD `skipEmptyFiles` int(1) unsigned NOT NULL DEFAULT '1',
ADD `syncToDest` int(1) unsigned NOT NULL DEFAULT '0';

/*!40000 ALTER TABLE `OVDM_CruiseDataTransfers` ENABLE KEYS */;
UNLOCK TABLES;

# Add columnes to table OVDM_ExtraDirectories
# ------------------------------------------------------------

LOCK TABLES `OVDM_ExtraDirectories` WRITE;
/*!40000 ALTER TABLE `OVDM_ExtraDirectories` DISABLE KEYS */;
ALTER TABLE `OVDM_ExtraDirectories`
ADD `cruiseOrLowering` int(1) unsigned NOT NULL DEFAULT '0';

/*!40000 ALTER TABLE `OVDM_ExtraDirectories` ENABLE KEYS */;
UNLOCK TABLES;