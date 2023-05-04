# Remove PublicDataDir from table OVDM_CoreVars
# ------------------------------------------------------------
LOCK TABLES `OVDM_CoreVars` WRITE;
/*!40000 ALTER TABLE `OVDM_CoreVars` DISABLE KEYS */;

DELETE FROM `OVDM_CoreVars` WHERE name='shipboardDataWarehousePublicDataDir';
INSERT INTO `OVDM_CoreVars` (`name`, `value`) VALUES
  ('cruiseStartPort','Newport, RI'),
  ('cruiseEndPort','Norfolk, VA');

/*!40000 ALTER TABLE `OVDM_CoreVars` ENABLE KEYS */;
UNLOCK TABLES;

LOCK TABLES `OVDM_CollectionSystemTransfers` WRITE;
/*!40000 ALTER TABLE `OVDM_CollectionSystemTransfers` DISABLE KEYS */;
ALTER TABLE `OVDM_CollectionSystemTransfers`
ADD `removeSourceFiles` int(1) unsigned NOT NULL DEFAULT '0';

/*!40000 ALTER TABLE `OVDM_CollectionSystemTransfers` ENABLE KEYS */;
UNLOCK TABLES;
