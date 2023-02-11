# Add columnes to table OVDM_CollectionSystemTransfers
# ------------------------------------------------------------

LOCK TABLES `OVDM_CollectionSystemTransfers` WRITE;
/*!40000 ALTER TABLE `OVDM_CollectionSystemTransfers` DISABLE KEYS */;
ALTER TABLE `OVDM_CollectionSystemTransfers`
ADD `removeSourceFiles` int(1) unsigned NOT NULL DEFAULT '0';

/*!40000 ALTER TABLE `OVDM_CollectionSystemTransfers` ENABLE KEYS */;
UNLOCK TABLES;