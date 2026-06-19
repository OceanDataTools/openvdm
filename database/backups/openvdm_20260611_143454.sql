/*M!999999\- enable the sandbox mode */ 
-- MariaDB dump 10.19-11.8.6-MariaDB, for debian-linux-gnu (x86_64)
--
-- Host: localhost    Database: openvdm
-- ------------------------------------------------------
-- Server version	11.8.6-MariaDB-0+deb13u1 from Debian

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*M!100616 SET @OLD_NOTE_VERBOSITY=@@NOTE_VERBOSITY, NOTE_VERBOSITY=0 */;

--
-- Table structure for table `OVDM_CollectionSystemTransfers`
--

DROP TABLE IF EXISTS `OVDM_CollectionSystemTransfers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `OVDM_CollectionSystemTransfers` (
  `collectionSystemTransferID` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `name` tinytext NOT NULL,
  `longName` text DEFAULT NULL,
  `cruiseOrLowering` int(1) unsigned NOT NULL DEFAULT 0,
  `sourceDir` tinytext DEFAULT NULL,
  `destDir` tinytext DEFAULT NULL,
  `staleness` int(11) DEFAULT 0,
  `removeSourceFiles` int(1) unsigned NOT NULL DEFAULT 0,
  `useStartDate` tinyint(1) DEFAULT 0,
  `skipEmptyDirs` int(1) unsigned NOT NULL DEFAULT 1,
  `skipEmptyFiles` int(1) unsigned NOT NULL DEFAULT 1,
  `syncFromSource` int(1) unsigned NOT NULL DEFAULT 0,
  `transferType` int(11) unsigned NOT NULL,
  `localDirIsMountPoint` int(1) unsigned NOT NULL DEFAULT 0,
  `rsyncServer` tinytext DEFAULT NULL,
  `rsyncUser` tinytext DEFAULT NULL,
  `rsyncPass` tinytext DEFAULT NULL,
  `smbServer` tinytext DEFAULT NULL,
  `smbUser` tinytext DEFAULT NULL,
  `smbPass` tinytext DEFAULT NULL,
  `smbDomain` tinytext DEFAULT NULL,
  `sshServer` tinytext DEFAULT NULL,
  `sshUser` tinytext DEFAULT NULL,
  `sshUseKey` int(1) unsigned NOT NULL DEFAULT 0,
  `sshPass` tinytext DEFAULT NULL,
  `includeFilter` text DEFAULT NULL,
  `excludeFilter` text DEFAULT NULL,
  `ignoreFilter` text DEFAULT NULL,
  `status` int(11) unsigned NOT NULL DEFAULT 3,
  `enable` tinyint(1) NOT NULL DEFAULT 0,
  `pid` int(11) unsigned DEFAULT 0,
  `bandwidthLimit` int(10) unsigned NOT NULL DEFAULT 0,
  PRIMARY KEY (`collectionSystemTransferID`),
  KEY `CollectionSystemTransferStatus` (`status`),
  KEY `CollectionSystemTransferType` (`transferType`),
  CONSTRAINT `CollectionSystemTransferStatus` FOREIGN KEY (`status`) REFERENCES `OVDM_Status` (`statusID`),
  CONSTRAINT `CollectionSystemTransferType` FOREIGN KEY (`transferType`) REFERENCES `OVDM_TransferTypes` (`transferTypeID`)
) ENGINE=InnoDB AUTO_INCREMENT=87 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `OVDM_CollectionSystemTransfers`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `OVDM_CollectionSystemTransfers` WRITE;
/*!40000 ALTER TABLE `OVDM_CollectionSystemTransfers` DISABLE KEYS */;
INSERT INTO `OVDM_CollectionSystemTransfers` VALUES
(1,'UHDAS_1','Acoustics - UHDAS1',0,'/home/data/{cruiseID}*','Falkor_too/Raw/ADCP',5,0,0,1,1,0,4,0,'','','','','','','','10.23.10.73','adcp',0,'soi_uh14.','*','.nfs*','*00mount_test*,*archive_dailyreports/*',2,1,0,0),
(2,'SBE_CTD','Oceanography - CTD',0,'CTD/Raw/{cruiseID}','Falkor_too/Raw/CTD',5,0,0,1,1,0,3,0,'','','','//10.23.10.75/D','localuser','CTD4Science!','WORKGROUP','','',0,'','*,*.hex,*.asvp','','',2,1,0,0),
(5,'EK80','Acoustics - EK80',0,'EK80/{cruiseID}','Falkor_too/Raw/EK80',5,1,0,1,1,0,3,0,'','','','//10.23.10.66/D','Operator','simrad0','WORKGROUP','','',0,'','*','','',4,0,0,0),
(6,'EM124','Acoustics - EM124',0,'sisdata/raw/{cruiseID}','Falkor_too/Raw/EM124/',5,0,0,1,1,0,3,0,'','','','//10.23.10.60/D$','Operator','simrad0','WORKGROUP','','',0,'','*','*kmwcd_frag','*9999.kmall,*.asvp*,*.temp*,*.abs*,*kmwcd_frag',2,1,0,0),
(8,'EM124_Bist','Acoustics - EM124 - BIST',0,'sisdata/common/BIST/{cruiseID}','Falkor_too/Raw/EM124/Bist_Results',0,0,0,1,1,0,3,0,'','','','//10.23.10.60/D$','Operator','simrad0','WORKGROUP','','',0,'','*','','',2,1,0,0),
(9,'EM712','Acoustics - EM712',0,'sisdata/raw/{cruiseID}','Falkor_too/Raw/EM712',5,0,0,1,1,0,3,0,'','','','//10.23.10.62/D$','Operator','simrad0','WORKGROUP','','',0,'','*','','*.asvp,*.temp,*.abs,*9999.kmall,*kmwcd_frag',2,1,0,0),
(11,'EM712_BIST','Acoustics - EM712 - BIST',0,'sisdata/common/BIST/{cruiseID}','Falkor_too/Raw/EM712/Bist_Results',5,0,0,1,1,0,3,0,'','','','//10.23.10.62/D','Operator','simrad0','WORKGROUP','','',0,'','*','','',2,1,0,0),
(14,'SBP29','Acoustics - SBP29',0,'SBP29/{cruiseID}','Falkor_too/Raw/SBP29',5,0,0,1,1,0,3,0,'','','','//10.23.10.69/e$','Operator','simrad0','WORKGROUP','','',0,'','*','','',2,1,0,0),
(17,'pH','Oceanography - pH',0,'{cruiseID}/AFT_pH_2_AP0013','Falkor_too/Raw/pH',5,0,1,1,1,0,3,0,'','','','//10.23.10.52/pH','localuser','admin4@llMT!','WORKGROUP','','',0,'','*','','',4,0,0,0),
(18,'POSMV_PPP','Navigation - POSMV - PPP',0,'{cruiseID}','Falkor_too/Raw/POSMV',5,0,1,1,1,0,3,0,'','','','//10.23.10.52/POSMV_PPP_RAW','localuser','admin4@llMT!','WORKGROUP','','',0,'','*','','',2,1,0,0),
(19,'Processed_MB','Processed - Multibeam - Final',0,'{cruiseID}','Falkor_too/Processed/Final/Final_MB_Products',0,0,0,1,1,0,3,0,'','','','//10.23.9.62/Multibeam-final-data-for-CruiseData-sync','operator','Simrad2022','ad.falkortoo.org','','',0,'','*','','',2,1,0,0),
(21,'OpenRVDAS','CruiseFiles - OpenRVDAS',0,'/data/openrvdas','Falkor_too/Raw/OpenRVDAS',0,0,1,1,1,0,4,0,'','','','','','','','10.23.9.21','mt',0,'Dragon2017','*{cruiseID}_*.txt,*{cruiseID}_*.bin','','',2,1,0,0),
(22,'SVX2','Oceanography - SVX2',0,'CTD_SVX2/{cruiseID}','Falkor_too/Raw/SVP',5,0,1,1,1,0,3,0,'','','','//10.23.10.75/D','localuser','Dragon2026!!!','WORKGROUP','','',0,'','*/{cruiseID}_[0-9][0-9][0-9].pro,*/{cruiseID}_{loweringID}_SVP_ROV_DOWNCAST.pro,*/{cruiseID}_[0-9][0-9][0-9]*kHz.abs,*/{cruiseID}_{loweringID}_SVP_ROV_DOWNCAST*kHz.abs','','*.bsvp,*.asvp',4,0,0,0),
(24,'XBT','Oceanography - XBT',0,'XBT/{cruiseID}','Falkor_too/Raw/XBT',5,0,1,0,0,1,3,0,'','','','//10.23.10.75/D','localuser','CTD4Science!','WORKGROUP','','',0,'','*{cruiseID}.db,*{cruiseID}_[0-9][0-9][0-9].nc,*{cruiseID}_[0-9][0-9][0-9].csv,*{cruiseID}_[0-9][0-9][0-9].jjv,*{cruiseID}_[0-9][0-9][0-9].svp,*{cruiseID}/dropStatus.csv,*export/{cruiseID}.kml,*','pseudofileXXXXXX','',2,1,0,0),
(25,'S5K_SCICAM_DVR','ROV - DVR - SCI Cam',1,'/home/soi/videos','Video/SCICAM',5,1,1,1,1,0,4,0,'','','','','','','','10.23.46.60','soi',0,'SOI4awesome','*.mov','','',2,1,0,37500),
(29,'UHDAS_2','Acoustics - UHDAS2',0,'/home/data/{cruiseID}*-no-EEZ','Falkor_too/Raw/ADCP_BKUP',0,0,0,0,0,0,4,0,'','','','','','','','10.23.10.74','adcp',0,'soi_uh14.','*','','*00mount_test*,*archive_dailyreports/*,*0uhdas/*',4,0,0,0),
(30,'EA440','Acoustics - EA440',0,'EA440/{cruiseID}','Falkor_too/Raw/EA440',20,0,1,0,0,0,3,0,'','','','//10.23.10.67/G$','Operator','simrad0','WORKGROUP','','',0,'','*.raw,*.idx','','',4,0,0,0),
(31,'EA640','Acoustics - EA640',0,'EA640/{cruiseID}','Falkor_too/Raw/EA640',0,0,0,0,0,0,3,0,'','','','//10.23.10.68/G$','Operator','simrad0','WORKGROUP','','',0,'','*L[0-9][0-9][0-9][0-9]-{cruiseID}-D[2-3][0-9][0-1][0-9][0-3][0-9]-T[0-2][0-3][0-5][0-9][0-9][0-9].raw,*L[0-9][0-9][0-9][0-9]-{cruiseID}-D[2-3][0-9][0-1][0-9][0-3][0-9]-T[0-2][0-3][0-5][0-9][0-9][0-9].idx','','',4,0,0,0),
(32,'EM2040','Acoustics - EM2040',0,'sisdata/raw/{cruiseID}','Falkor_too/Raw/EM2040',5,1,0,1,1,0,3,0,'','','','//10.23.10.64/E$','Operator','simrad0','WORKGROUP','','',0,'','*_{cruiseID}_EM2040.*','','*9999.kmall,*.asvp*,*.temp*,*.abs*,*kmwcd_frag',4,0,0,0),
(33,'EM2040_Bist','Acoustics - EM2040 - BIST',0,'sisdata/common/BIST/{cruiseID}','Falkor_too/Raw/EM2040/Bist_Results',0,0,0,1,1,0,3,0,'','','','//10.23.10.64/E$','Operator','simrad0','WORKGROUP','','',0,'','*','','',4,0,0,0),
(35,'S5K_SITCAM_DVR','ROV - DVR - SIT Cam',1,'/home/soi/videos/','Video/SITCAM',5,1,1,1,1,0,4,0,'','','','','','','','10.23.46.61','soi',0,'SOI4awesome','*.mov','','',2,1,0,37500),
(36,'S5K_HDQUAD_DVR','ROV - DVR - HD Quad',1,'/home/soi/videos','Video/HDQUAD',5,1,1,1,1,0,4,0,'','','','','','','','10.23.46.62','soi',1,NULL,'*.mov','','',4,0,0,37500),
(37,'S5K_SDQUAD_DVR','ROV - DVR - SD Quad',1,'/home/soi/videos','Video/SDQUAD',5,1,1,1,1,0,4,0,'','','','','','','','10.23.46.63','soi',1,NULL,'*.mov','','',4,0,0,37500),
(38,'S5K_SCITOO_DVR','ROV - DVR - SCI Too',1,'/home/soi/videos','Video/SCITOO',5,1,1,1,1,0,4,0,'','','','','','','','10.23.46.64','soi',1,NULL,'*.mov','','',4,0,0,37500),
(39,'S5K_SITTOO_DVR','ROV - DVR - SIT Too',1,'/home/soi/videos','Video/SITTOO',5,1,1,1,1,0,4,0,'','','','','','','','10.23.46.65','soi',0,'SOI4awesome','*.mov','','',4,0,0,37500),
(40,'PI_NAS_PARTICIPANT','CruiseFiles - Participant - PINAS',0,'/net/PI-NAS/{cruiseID}/ParticipantData','ParticipantData',5,0,0,0,0,1,1,0,'','','','','','','','','',0,'','*','*.exe,*.bat,*.pkg,*.img,*@eaDir*','*/.DS_Store,*/Thumbs.db,.rsync,lost+found,lost?found,.Spotlight-V100,.fseventsd,.Trash,1000,.Trashes,._.Trashes,.TemporaryItems,._.TemporaryItems,.DS_Store,Thumbs.db,ld.so.cache,.Recycle_Bin,$RECYCLE.BIN,.@__thumb,*.pvm,Backups.backupdb,@eaDir,@SynoEAStream,@SynoResource,@SynoEAStream',4,0,0,0),
(41,'EM124_SRH','Acoustics - EM124 - SRH',0,'sisdata/common/srh','Falkor_too/Raw/EM124/SRH/',0,0,1,1,1,0,3,0,'','','','//10.23.10.60/D$','Operator','simrad0','WORKGROUP','','',0,'','*','','',2,1,0,0),
(42,'EM712_SRH','Acoustics - EM712 - SRH',0,'sisdata/common/srh','Falkor_too/Raw/EM712/SRH/',0,0,1,1,1,0,3,0,'','','','//10.23.10.62/D','Operator','simrad0','WORKGROUP','','',0,'','*','','',2,1,0,0),
(43,'EM2040_SRH','Acoustics - EM2040 - SRH',0,'sisdata/common/srh','Falkor_too/Raw/EM2040/SRH/',0,0,1,1,1,0,3,0,'','','','//10.23.10.64/E$','Operator','simrad0','WORKGROUP','','',0,'','*','','',4,0,0,0),
(44,'SCI-NAV-Multibeam','ROV - M3',1,'M3/{cruiseID}/','M3',5,1,1,1,1,0,3,0,'','','','//10.23.9.70/f','openvdm','Dragon2017','WORKGROUP','','',0,'','*','','',4,0,0,0),
(45,'Working_MB','Processed - Multibeam - Working',0,'{cruiseID}','Falkor_too/Processed/Preliminary/Processed_MB',5,0,0,1,1,0,3,0,'','','','//10.23.9.62/multibeam-working-data-sync','operator','Simrad2022','ad.falkortoo.org','','',0,'','*','','',2,1,0,0),
(46,'ROV_Sprint_Raw','ROV - SPRINT - Raw',1,'Hub/Logfiles','Sprint',5,0,1,0,0,0,3,0,'','','','//10.23.48.20/Sonardyne','localuser','admin4@llMT','WORKGROUP','','',0,'','*.bin','','',2,1,0,0),
(47,'SCI-NAV-ADCP','ROV - SYRINX',1,'{cruiseID}/Syrinx','Syrinx',5,1,1,1,1,0,3,0,'','','','//10.23.9.70/f','localuser','admin4@llMT','WORKGROUP','','',0,'','*.pd0','','',4,0,0,0),
(51,'Processed_CTD','Oceanography - CTD - Processed',0,'CTD/Processed/{cruiseID}','Falkor_too/Processed/Preliminary/Processed_CTD',0,0,0,1,1,0,3,0,'','','','//10.23.10.75/D','localuser','CTD4Science!','WORKGROUP','','',0,'','*','','',2,1,0,0),
(52,'PSONNAV_4DNav','ROV - PSONNAV - 4DNAV',1,'4DNAV_Projects/Setup_Aug_2025/Local/Station/Data/RawData/PSONNAV_INS_Direct','Sprint/PSONNAV',0,0,1,0,0,0,3,0,'','','','//10.23.10.24/D','operator','Simrad2022','ad.falkortoo.org','','',0,'','*','','',4,0,0,0),
(54,'SBP29-Processed','Acoustics - SBP29 - SEGY',0,'{cruiseID}','Falkor_too/Processed/Preliminary/Processed_SBP29',5,0,0,1,1,0,3,0,'','','','//10.23.10.69/f$','Operator','simrad0','WORKGROUP','','',0,'','*','','',2,1,0,0),
(58,'Working-M3','Processed - M3 - Working',0,'{cruiseID}','Falkor_too/Processed/Preliminary/Processed_M3',5,0,0,0,1,0,3,0,'','','','//10.23.9.62/M3-working-data-sync/','operator','Simrad2022','ad.falkortoo.org','','',0,'','*','.nfs*','',4,0,0,0),
(59,'M3-Final','Processed - M3  - Final',0,'{cruiseID}','Falkor_too/Processed/Final/Final_MB_Products/Final_M3',5,0,0,0,1,0,3,0,'','','','//10.23.9.62/M3-final-data-for-CruiseData-sync/','operator','Simrad2022','ad.falkortoo.org','','',0,'','*','','',4,0,0,0),
(61,'Exported_SSP_from_SSM','Oceanography - SSM Exports',0,'{cruiseID}','Falkor_too/Processed/Preliminary/Sound_Speed_Files/',5,0,1,1,1,0,3,0,'','','','//10.23.9.27/SSM_SVP','operator','simrad0','WORKGROUP','','',0,'','*/{cruiseID}_CTD_[0-9][0-9][0-9]*,*/{cruiseID}_{loweringID}_SVP_ROV_DOWNCAST.bsvp,*/{cruiseID}_{loweringID}_SVP_ROV_DOWNCAST.asvp,*','','',2,1,0,0),
(62,'SAMOS','Oceanography - SAMOS',0,'/data/samos/','Falkor_too/Processed/SAMOS/',5,0,1,1,1,0,4,0,'','','','','','','','10.23.9.24','mt',0,'Dragon2017','*.csv','','',2,1,0,0),
(65,'mTail-ROV','Oceanography - mTAIL - ROV',1,'mTail/ROV/{cruiseID}/{loweringID}','mTail',0,0,0,0,0,0,3,0,'','','','//10.23.10.75/D','localuser','admin4@llMT!','WORKGROUP','','',0,'','*','','',4,0,0,0),
(66,'mTail-CTD','Oceanography - mTAIL - CTD',0,'mTail/CTD/{cruiseID}/','Falkor_too/Raw/mTail',0,0,0,0,0,0,3,0,'','','','//10.23.10.75/D','localuser','admin4@llMT!','WORKGROUP','','',0,'','*','','',4,0,0,0),
(71,'Greensea_Missions','ROV - Greensea',1,'Greensea/{cruiseID}/{loweringID}','Greensea',0,0,0,0,0,0,3,0,'','','','//10.23.9.70/f','localuser','admin4@llMT','WORKGROUP','','',0,'','*','','',4,0,0,0),
(72,'Processed_CTD_Figures','Oceanography - CTD - Figures',0,'CTD/Figures/{cruiseID}','Falkor_too/Processed/Preliminary/Processed_CTD',0,0,0,1,1,0,3,0,'','','','//10.23.10.75/D','localuser','CTD4Science!','WORKGROUP','','',0,'','*','','',2,1,0,0),
(73,'ASCISYN_PARTICIPANT','CruiseFiles - Participant -  ASCISYN',0,'/mnt/CruiseSandbox/ParticipantData','ParticipantData',5,0,0,0,0,1,1,0,'','','','','','','','','',0,'','*','*.exe,*.bat,*.pkg,*.img,*@eaDir*','*/.DS_Store,*/Thumbs.db,.rsync,lost+found,lost?found,.Spotlight-V100,.fseventsd,.Trash,1000,.Trashes,._.Trashes,.TemporaryItems,._.TemporaryItems,.DS_Store,Thumbs.db,ld.so.cache,.Recycle_Bin,$RECYCLE.BIN,.@__thumb,*.pvm,Backups.backupdb,@eaDir,@SynoEAStream,@SynoResource,@SynoEAStream,*/@eaDir',2,1,0,0),
(76,'Mapr','Oceanography - MAPR',1,'/mnt/CruiseSandbox/mapr/{loweringID}','mapr',5,0,0,0,0,0,1,0,'','','','','','','','','',0,'','*','','.rsync,lost+found,lost?found,.Spotlight-V100,.fseventsd,.Trash,1000,.Trashes,._.Trashes,.TemporaryItems,._.TemporaryItems,ld.so.cache,.Recycle_Bin,$RECYCLE.BIN,.@__thumb,*.pvm,Backups.backupdb,@SynoEAStream,@SynoResource,@SynoEAStream',4,0,0,0),
(77,'Equipment_MASH','Equipment - East Coast Winch Logger MASH',0,'/Data','Falkor_too/Raw/Winch/Mash',5,0,1,1,1,0,4,0,'','','','','','','','10.23.10.81','mt',0,'Dragon2025','*MASH*','','',2,1,0,0),
(78,'Equipment_MERMAC','Equipment - East Coast Winch Logger MERMAC',0,'/Data','Falkor_too/Raw/Winch/Mermac',5,0,1,1,1,0,4,0,'','','','','','','','10.23.10.81','mt',0,'Dragon2025','*MERMAC*','','',2,1,0,0),
(79,'Equipment_ODIM','Equipment - East Coast Winch Logger ODIM',0,'/Data','Falkor_too/Raw/Winch/Odim_ROV',5,0,1,1,1,0,4,0,'','','','','','','','10.23.10.81','mt',0,'Dragon2025','*ROV*','','',2,1,0,0),
(80,'Magnetometer','Geophysical - Magnetometer',0,'magnetometer/{cruiseID}','Falkor_too/Raw/Magnetometer',5,0,0,1,1,0,3,0,'','','','//10.23.10.75/D','localuser','Dragon2017!!','WORKGROUP','','',0,'','*.*','','',4,0,0,0),
(81,'Working_SBP','Processed - SBP - Working',0,'{cruiseID}_SBP29','Falkor_too/Processed/Preliminary/Processed_SBP',5,0,0,1,1,0,3,0,'','','','//10.23.9.62/SBP29-working-data-sync','operator','Simrad2022','ad.falkortoo.org','','',0,'','*','','',4,0,0,0),
(83,'AUV_EMPSYN_Missions','AUV - EMPSYN - Missions',0,'/net/empsyn/{cruiseID}','Vehicles/Empress/',0,0,0,0,0,0,1,0,'','','','','','','','','',0,'','*','*/HISASRaw/*','',2,1,0,0),
(84,'Lander_Shirkry_Camera','Lander - Shirkry - Camera',0,'Lander/Shirkry/{cruiseID}','Vehicles/Shirkry/',5,0,0,0,0,0,3,0,'','','','//10.23.10.75/D','localuser','Dragon2017!!','WORKGROUP','','',0,'','*','','',4,0,0,0),
(85,'pCO2','Oceanography - pCO2',0,'{cruiseID}','Falkor_too/Raw/pCO2',5,0,1,1,1,0,3,0,'','','','//10.23.11.79/C/data','operator','simrad0','WORKGROUP','','',0,'','*','','',2,1,0,0),
(86,'AUV_EMPSYN_HiSAS_RAW','AUV - EMPSYN - HiSAS Raw',0,'/net/empsyn/{cruiseID}','Vehicles/Empress/',0,0,0,0,0,0,1,0,'','','','','','','','','',0,'','*/HISASRaw/*','','',2,1,0,0);
/*!40000 ALTER TABLE `OVDM_CollectionSystemTransfers` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `OVDM_CoreVars`
--

DROP TABLE IF EXISTS `OVDM_CoreVars`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `OVDM_CoreVars` (
  `coreVarID` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `name` tinytext NOT NULL,
  `value` tinytext DEFAULT NULL,
  PRIMARY KEY (`coreVarID`)
) ENGINE=InnoDB AUTO_INCREMENT=24 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `OVDM_CoreVars`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `OVDM_CoreVars` WRITE;
/*!40000 ALTER TABLE `OVDM_CoreVars` DISABLE KEYS */;
INSERT INTO `OVDM_CoreVars` VALUES
(1,'shipboardDataWarehouseIP','10.128.0.69'),
(2,'shipboardDataWarehouseUsername','mt'),
(3,'shipboardDataWarehouseStatus','2'),
(4,'cruiseID','FKt999999'),
(5,'cruiseName','Test Cruise'),
(6,'cruiseStartDate','2026/06/10 00:00'),
(7,'cruiseStartPort','here'),
(8,'cruiseEndDate','2026/06/24 11:15'),
(9,'cruiseEndPort','there'),
(10,'cruisePI','Corrine Bassin'),
(11,'cruiseLocation','Google Cloud'),
(12,'cruiseSize','6714'),
(13,'cruiseSizeUpdated','2026/06/11 14:34:44'),
(14,'loweringID','S9999'),
(15,'loweringStartDate','2026/06/10 11:00'),
(16,'loweringEndDate',''),
(17,'loweringSize','1271'),
(18,'loweringSizeUpdated','2026/06/11 14:34:44'),
(19,'systemStatus','Off'),
(20,'shipToShoreBWLimitStatus','Off'),
(21,'md5FilesizeLimit','10'),
(22,'md5FilesizeLimitStatus','On'),
(23,'showLoweringComponents','Yes');
/*!40000 ALTER TABLE `OVDM_CoreVars` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `OVDM_CruiseDataTransfers`
--

DROP TABLE IF EXISTS `OVDM_CruiseDataTransfers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `OVDM_CruiseDataTransfers` (
  `cruiseDataTransferID` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `name` tinytext NOT NULL,
  `longName` text DEFAULT NULL,
  `skipEmptyDirs` int(1) unsigned NOT NULL DEFAULT 1,
  `skipEmptyFiles` int(1) unsigned NOT NULL DEFAULT 1,
  `syncToDest` int(1) unsigned NOT NULL DEFAULT 0,
  `transferType` int(11) unsigned NOT NULL,
  `destDir` tinytext DEFAULT NULL,
  `localDirIsMountPoint` int(1) unsigned NOT NULL DEFAULT 0,
  `rsyncServer` tinytext DEFAULT NULL,
  `rsyncUser` tinytext DEFAULT NULL,
  `rsyncPass` tinytext DEFAULT NULL,
  `smbServer` tinytext DEFAULT NULL,
  `smbUser` tinytext DEFAULT NULL,
  `smbPass` tinytext DEFAULT NULL,
  `smbDomain` tinytext DEFAULT NULL,
  `sshServer` tinytext DEFAULT NULL,
  `sshUser` tinytext DEFAULT NULL,
  `sshUseKey` int(1) unsigned NOT NULL DEFAULT 0,
  `sshPass` tinytext DEFAULT NULL,
  `status` int(11) unsigned NOT NULL DEFAULT 3,
  `enable` tinyint(1) NOT NULL DEFAULT 0,
  `required` tinyint(1) NOT NULL DEFAULT 0,
  `pid` int(11) unsigned DEFAULT 0,
  `bandwidthLimit` int(10) unsigned NOT NULL DEFAULT 0,
  `includeOVDMFiles` int(1) unsigned NOT NULL DEFAULT 0,
  `includePublicDataFiles` int(1) unsigned NOT NULL DEFAULT 0,
  `excludedCollectionSystems` tinytext DEFAULT NULL,
  `excludedExtraDirectories` tinytext DEFAULT NULL,
  PRIMARY KEY (`cruiseDataTransferID`),
  KEY `CruiseDataTransferStatus` (`status`),
  KEY `CruiseDataTransferType` (`transferType`),
  CONSTRAINT `CruiseDataTransferStatus` FOREIGN KEY (`status`) REFERENCES `OVDM_Status` (`statusID`),
  CONSTRAINT `CruiseDataTransferType` FOREIGN KEY (`transferType`) REFERENCES `OVDM_TransferTypes` (`transferTypeID`)
) ENGINE=InnoDB AUTO_INCREMENT=49 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `OVDM_CruiseDataTransfers`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `OVDM_CruiseDataTransfers` WRITE;
/*!40000 ALTER TABLE `OVDM_CruiseDataTransfers` DISABLE KEYS */;
INSERT INTO `OVDM_CruiseDataTransfers` VALUES
(1,'SSDW','Shoreside Data Warehouse',1,1,0,4,'fkt251206:',0,'','','','','','','','fkt251206:','mt',0,'dragon',4,0,1,0,25600,0,0,'0','0'),
(2,'GTA','Google Transfer Appliance (GTA)',0,0,0,1,'/net/GTA',1,'','','','','','','','','',0,'',2,1,0,0,0,1,0,'',''),
(10,'soi_data2','Archive on soi_data2',0,0,0,1,'/mnt/soi_data2',1,'','','','','','','','','',0,'',4,0,0,0,0,1,0,'38,39',''),
(11,'soi_data3','Archive on soi_data3',0,0,0,1,'/mnt/soi_data3',1,'','','','','','','','','',0,'',4,0,0,0,0,1,0,'38,37',''),
(12,'soi_data4','Archive on soi_data4',0,0,0,1,'/mnt/soi_data4',1,'','','','','','','','','',0,'',4,0,0,0,0,1,0,'38,39',''),
(25,'PINAS2','PINAS2',0,0,0,1,'/net/PINAS2',1,'','','','','','','','','',0,'',4,0,0,0,0,1,0,'38',''),
(26,'SCIQNAP','Science_QNAP',0,0,0,4,'/share/CruiseData',0,'','','','','','','','10.23.9.13','admin',0,'N0ct1luca2023!',3,0,0,0,0,1,0,'',''),
(28,'ObserverNas','ObserverNas',0,0,1,1,'/net/ObserverNAS',1,'','','','','','','','','',0,'',2,1,0,0,0,1,0,'37',''),
(30,'ObserverNas_USB1_CruiseData','ObserverNas_USB1_CruiseData',0,0,0,1,'/net/ObserverNAS_USB1_CruiseData',0,'','','','','','','','','',0,'',3,0,0,0,0,1,0,'73',''),
(35,'ObserverNas2','ObserverNas2',0,0,1,1,'/net/ObserverNAS2',1,'','','','','','','','','',0,'',3,0,0,0,0,1,0,'',''),
(36,'PINAS','PINAS',0,0,0,1,'/net/PINAS',1,'','','','','','','','','',0,'',2,1,0,0,0,1,0,'37',''),
(37,'soi_data1','Archive on soi_data1',0,0,0,1,'/mnt/soi_data1',1,'','','','','','','','','',0,'',2,1,0,0,0,1,0,'',''),
(39,'PINAS_USB1_CruiseData','PINAS_USB1_CruiseData',0,0,0,1,'/net/PINAS_USB1_CruiseData',0,'','','','','','','','','',0,'',4,0,0,0,0,1,0,'',''),
(40,'ObserverNas2_USB1_CruiseData','ObserverNas2_USB1_CruiseData',0,0,0,1,'/net/ObserverNAS2_USB1_CruiseData',0,'','','','','','','','','',0,'',4,0,0,0,0,1,0,'73',''),
(42,'PINAS2_USB1_CruiseData','PINAS2_USB1_CruiseData',0,0,0,1,'/net/PINAS2_USB1_CruiseData',0,'','','','','','','','','',0,'',4,0,0,0,0,1,0,'',''),
(44,'PINAS2_USB2_CruiseData','PINAS2_USB2_CruiseData',0,0,0,1,'/net/PINAS2_USB2_CruiseData',0,'','','','','','','','','',0,'',3,0,0,0,0,1,0,'',''),
(45,'PINAS_USB2_CruiseData','PINAS_USB2_CruiseData',0,0,0,1,'/net/PINAS_USB2_CruiseData',0,'','','','','','','','','',0,'',3,0,0,0,0,1,0,'',''),
(46,'ObserverNas2_USB2_CruiseData','ObserverNas2_USB2_CruiseData',0,0,0,1,'/net/ObserverNas2_USB2_CruiseData',0,'','','','','','','','','',0,'',3,0,0,0,0,1,0,'73',''),
(47,'ObserverNas_USB2_CruiseData','ObserverNas_USB2_CruiseData',0,0,0,1,'/net/ObserverNAS_USB2_CruiseData',0,'','','','','','','','','',0,'',3,0,0,0,0,1,0,'73',''),
(48,'GoogleCloudSync','GoogleCloudSync',0,0,1,1,'SSDW-GC:ship-shore-transfer/',0,'','','','','','','','','',0,'',4,0,0,0,1650,1,0,'73,83,71,84,59,76,66,65,40,51,72,19,52,46,36,25,38,37,35,39,58,45,81','2,3,1');
/*!40000 ALTER TABLE `OVDM_CruiseDataTransfers` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `OVDM_ExtraDirectories`
--

DROP TABLE IF EXISTS `OVDM_ExtraDirectories`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `OVDM_ExtraDirectories` (
  `extraDirectoryID` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `name` tinytext NOT NULL,
  `longName` tinytext DEFAULT NULL,
  `cruiseOrLowering` int(1) unsigned NOT NULL DEFAULT 0,
  `destDir` tinytext DEFAULT NULL,
  `enable` tinyint(1) DEFAULT 0,
  `required` tinyint(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`extraDirectoryID`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `OVDM_ExtraDirectories`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `OVDM_ExtraDirectories` WRITE;
/*!40000 ALTER TABLE `OVDM_ExtraDirectories` DISABLE KEYS */;
INSERT INTO `OVDM_ExtraDirectories` VALUES
(1,'Dashboard_Data','Dashboard Data',0,'OpenVDM/DashboardData',1,1),
(2,'From_PublicData','Files copied from ParticipantData share',0,'ParticipantData',1,1),
(3,'ROV_OpenRVDAS_Data','Cropped OpenRVDAS data for ROV dives',1,'OpenRVDAS',0,0),
(4,'Tracklines','Cruise Tracklines',0,'OpenVDM/Tracklines',0,0),
(5,'Sealog_ROV','Sealog - SuBastian',1,'Sealog',0,0),
(6,'Sealog_Falkor','Sealog - Vessel',0,'Falkor_too/Raw/Sealog',0,0);
/*!40000 ALTER TABLE `OVDM_ExtraDirectories` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `OVDM_Gearman`
--

DROP TABLE IF EXISTS `OVDM_Gearman`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `OVDM_Gearman` (
  `jobID` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `jobHandle` tinytext DEFAULT NULL,
  `jobKnown` tinyint(11) unsigned DEFAULT 1,
  `jobRunning` tinyint(11) unsigned DEFAULT 1,
  `jobNumerator` int(11) unsigned DEFAULT 0,
  `jobDenominator` int(11) unsigned DEFAULT 0,
  `jobName` tinytext DEFAULT NULL,
  `jobPid` int(11) unsigned DEFAULT NULL,
  PRIMARY KEY (`jobID`)
) ENGINE=InnoDB AUTO_INCREMENT=105 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `OVDM_Gearman`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `OVDM_Gearman` WRITE;
/*!40000 ALTER TABLE `OVDM_Gearman` DISABLE KEYS */;
/*!40000 ALTER TABLE `OVDM_Gearman` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `OVDM_Links`
--

DROP TABLE IF EXISTS `OVDM_Links`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `OVDM_Links` (
  `linkID` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `name` tinytext NOT NULL,
  `url` tinytext NOT NULL,
  `enable` tinyint(1) NOT NULL DEFAULT 0,
  `private` tinyint(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`linkID`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `OVDM_Links`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `OVDM_Links` WRITE;
/*!40000 ALTER TABLE `OVDM_Links` DISABLE KEYS */;
INSERT INTO `OVDM_Links` VALUES
(1,'Supervisord','http://{hostIP}:9001',1,1),
(2,'Participant Data','http://{hostIP}/ParticipantData/',1,0),
(3,'Cruise Data','http://{hostIP}/CruiseData/{cruiseID}/',1,0),
(4,'ScienceData','http://{hostIP}/ScienceData',0,0);
/*!40000 ALTER TABLE `OVDM_Links` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `OVDM_ShipToShoreTransfers`
--

DROP TABLE IF EXISTS `OVDM_ShipToShoreTransfers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `OVDM_ShipToShoreTransfers` (
  `shipToShoreTransferID` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `name` tinytext DEFAULT NULL,
  `longName` tinytext DEFAULT NULL,
  `priority` int(11) DEFAULT NULL,
  `collectionSystem` int(11) unsigned DEFAULT NULL,
  `extraDirectory` int(11) unsigned DEFAULT NULL,
  `includeFilter` tinytext DEFAULT NULL,
  `enable` tinyint(1) NOT NULL DEFAULT 0,
  `required` tinyint(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`shipToShoreTransferID`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `OVDM_ShipToShoreTransfers`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `OVDM_ShipToShoreTransfers` WRITE;
/*!40000 ALTER TABLE `OVDM_ShipToShoreTransfers` DISABLE KEYS */;
INSERT INTO `OVDM_ShipToShoreTransfers` VALUES
(1,'DashboardData','Dashboard Data',1,0,2,'*',1,1),
(2,'MD5Summary','MD5 Summary',1,0,0,'{md5_summary_fn},{md5_summary_md5_fn}',1,1),
(3,'OVDM_Config','OpenVDM Configuration',1,0,0,'{cruise_config_fn}',1,1),
(4,'cruise_tracklines','Cruise Tracklines',1,0,5,'*',0,0),
(5,'gcs_bucket','gcs-bucket',1,62,4,'*',0,0),
(6,'gcs_bucket_cal_docs','gcs_bucket_cal_docs',1,48,0,'*',0,0);
/*!40000 ALTER TABLE `OVDM_ShipToShoreTransfers` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `OVDM_Status`
--

DROP TABLE IF EXISTS `OVDM_Status`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `OVDM_Status` (
  `statusID` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `status` tinytext DEFAULT NULL,
  PRIMARY KEY (`statusID`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `OVDM_Status`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `OVDM_Status` WRITE;
/*!40000 ALTER TABLE `OVDM_Status` DISABLE KEYS */;
INSERT INTO `OVDM_Status` VALUES
(1,'Running'),
(2,'Idle'),
(3,'Error'),
(4,'Off'),
(5,'Stopping'),
(6,'Starting');
/*!40000 ALTER TABLE `OVDM_Status` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `OVDM_Tasks`
--

DROP TABLE IF EXISTS `OVDM_Tasks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `OVDM_Tasks` (
  `taskID` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `name` tinytext NOT NULL,
  `longName` tinytext NOT NULL,
  `cruiseOrLowering` tinyint(1) unsigned NOT NULL DEFAULT 0,
  `status` int(11) unsigned NOT NULL DEFAULT 3,
  `enable` tinyint(1) NOT NULL DEFAULT 0,
  `pid` int(10) unsigned NOT NULL DEFAULT 0,
  PRIMARY KEY (`taskID`),
  KEY `ProcessStatus` (`status`),
  CONSTRAINT `ProcessStatus` FOREIGN KEY (`status`) REFERENCES `OVDM_Status` (`statusID`)
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `OVDM_Tasks`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `OVDM_Tasks` WRITE;
/*!40000 ALTER TABLE `OVDM_Tasks` DISABLE KEYS */;
INSERT INTO `OVDM_Tasks` VALUES
(1,'setupNewCruise','Setup New {cruise_name}',0,2,1,0),
(2,'finalizeCurrentCruise','Finalize Current {cruise_name}',0,2,1,0),
(3,'rebuildMD5Summary','Rebuild MD5 Summary',0,2,1,0),
(4,'rebuildDataDashboard','Rebuild Data Dashboard',0,2,1,0),
(5,'rebuildCruiseDirectory','Rebuild {cruise_name} Directory',0,2,1,0),
(6,'exportOVDMConfig','Re-export the OpenVDM Configuration',0,2,1,0),
(7,'rsyncPublicDataToCruiseData','Sync ParticipantData within {cruise_name} Directory',0,2,1,0),
(8,'setupNewLowering','Setup New {lowering_name}',1,2,1,0),
(9,'finalizeCurrentLowering','Finalize Current {lowering_name}',1,2,1,0),
(10,'rebuildLoweringDirectory','Rebuild {lowering_name} Directory',1,3,1,0),
(11,'exportLoweringConfig','Re-export the {lowering_name} Configuration',1,2,1,0);
/*!40000 ALTER TABLE `OVDM_Tasks` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `OVDM_TransferTypes`
--

DROP TABLE IF EXISTS `OVDM_TransferTypes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `OVDM_TransferTypes` (
  `transferTypeID` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `transferType` tinytext DEFAULT NULL,
  PRIMARY KEY (`transferTypeID`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `OVDM_TransferTypes`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `OVDM_TransferTypes` WRITE;
/*!40000 ALTER TABLE `OVDM_TransferTypes` DISABLE KEYS */;
INSERT INTO `OVDM_TransferTypes` VALUES
(1,'Local Directory'),
(2,'Rsync Server'),
(3,'SMB Share'),
(4,'SSH Server');
/*!40000 ALTER TABLE `OVDM_TransferTypes` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `OVDM_Users`
--

DROP TABLE IF EXISTS `OVDM_Users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `OVDM_Users` (
  `userID` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `username` varchar(255) DEFAULT '',
  `password` varchar(255) DEFAULT '',
  `lastLogin` datetime DEFAULT NULL,
  PRIMARY KEY (`userID`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `OVDM_Users`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `OVDM_Users` WRITE;
/*!40000 ALTER TABLE `OVDM_Users` DISABLE KEYS */;
INSERT INTO `OVDM_Users` VALUES
(1,'mt','$2y$10$1/ZjvnYswUDHCjpciUHK5ue7XsD7hhiFEyi5cRtLBNSBF1ODhas4m','2026-06-11 14:21:43');
/*!40000 ALTER TABLE `OVDM_Users` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*M!100616 SET NOTE_VERBOSITY=@OLD_NOTE_VERBOSITY */;

-- Dump completed on 2026-06-11 14:34:54

/*M!999999\- enable the sandbox mode */ 
-- MariaDB dump 10.19-11.8.6-MariaDB, for debian-linux-gnu (x86_64)
--
-- Host: localhost    Database: openvdm
-- ------------------------------------------------------
-- Server version	11.8.6-MariaDB-0+deb13u1 from Debian

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*M!100616 SET @OLD_NOTE_VERBOSITY=@@NOTE_VERBOSITY, NOTE_VERBOSITY=0 */;

--
-- Table structure for table `OVDM_Messages`
--

DROP TABLE IF EXISTS `OVDM_Messages`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `OVDM_Messages` (
  `messageID` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `messageTitle` tinytext NOT NULL,
  `messageBody` text DEFAULT NULL,
  `messageTS` datetime NOT NULL,
  `messageViewed` tinyint(1) NOT NULL,
  PRIMARY KEY (`messageID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*M!100616 SET NOTE_VERBOSITY=@OLD_NOTE_VERBOSITY */;

-- Dump completed on 2026-06-11 14:34:54
