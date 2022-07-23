# Remove PublicDataDir from table OVDM_CoreVars
# ------------------------------------------------------------
LOCK TABLES `OVDM_CoreVars` WRITE;
/*!40000 ALTER TABLE `OVDM_CoreVars` DISABLE KEYS */;

DELETE FROM `OVDM_CoreVars` WHERE name='shipboardDataWarehousePublicDataDir';

/*!40000 ALTER TABLE `OVDM_CoreVars` ENABLE KEYS */;
UNLOCK TABLES;