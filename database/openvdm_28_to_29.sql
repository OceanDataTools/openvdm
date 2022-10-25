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