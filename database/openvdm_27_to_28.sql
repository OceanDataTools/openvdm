
# Add columnes to table OVDM_CollectionSystemTransfers
# ------------------------------------------------------------

LOCK TABLES `OVDM_CollectionSystemTransfers` WRITE;
/*!40000 ALTER TABLE `OVDM_CollectionSystemTransfers` DISABLE KEYS */;
ALTER TABLE `OVDM_CollectionSystemTransfers` ADD
`skipEmptyDirs` int(1) unsigned NOT NULL DEFAULT '1',
`skipEmptyFiles` int(1) unsigned NOT NULL DEFAULT '1',
`syncFromSource` int(1) unsigned NOT NULL DEFAULT '0';

/*!40000 ALTER TABLE `OVDM_CollectionSystemTransfers` ENABLE KEYS */;
UNLOCK TABLES;

# Add columnes to table OVDM_CruiseDataTransfers
# ------------------------------------------------------------

LOCK TABLES `OVDM_CruiseDataTransfers` WRITE;
/*!40000 ALTER TABLE `OVDM_CruiseDataTransfers` DISABLE KEYS */;
ALTER TABLE `OVDM_CruiseDataTransfers` ADD
`skipEmptyDirs` int(1) unsigned NOT NULL DEFAULT '1',
`skipEmptyFiles` int(1) unsigned NOT NULL DEFAULT '1',
`syncToDest` int(1) unsigned NOT NULL DEFAULT '0';

/*!40000 ALTER TABLE `OVDM_CruiseDataTransfers` ENABLE KEYS */;
UNLOCK TABLES;

# Add columnes to table OVDM_ExtraDirectories
# ------------------------------------------------------------

LOCK TABLES `OVDM_ExtraDirectories` WRITE;
/*!40000 ALTER TABLE `OVDM_ExtraDirectories` DISABLE KEYS */;
ALTER TABLE `OVDM_ExtraDirectories` ADD
`cruiseOrLowering` int(1) unsigned NOT NULL DEFAULT '0';

/*!40000 ALTER TABLE `OVDM_ExtraDirectories` ENABLE KEYS */;
UNLOCK TABLES;

# Add row to table OVDM_TransferTypes
# ------------------------------------------------------------

LOCK TABLES `OVDM_TransferTypes` WRITE;
/*!40000 ALTER TABLE `OVDM_TransferTypes` DISABLE KEYS */;

INSERT INTO `OVDM_TransferTypes` (`transferTypeID`, `transferType`)
VALUES
	(5,'FTP Server');

/*!40000 ALTER TABLE `OVDM_TransferTypes` ENABLE KEYS */;
UNLOCK TABLES;