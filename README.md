# Open Vessel Data Management

OpenVDM is a ship-wide data management platform.  It is comprised of a suite of programs and an accompanying web-application that provides vessel operators with a unified at-sea solution for retrieving and organizing files from multiple data acquisition systems into a unified cruise data package.  Once the files are within the cruise data package they are immediately and safely accessible by crew and scientists.  In addition OpenVDM can perform regularly backups of the cruise data package to one or more backup storage location/devices such as NAS arrays, external hard drives and even to shore-based servers.

![Home](/docs/OVDM_Home.png)

OpenVDM includes a plugin architecture whereby vessel operators can develop and install their own data processing plugins used to web-based visualizations, perform data quality assurance (QA) tests and collecting data statistics at the file-level.  In practice the output data from plugins is ~5% the size of the raw data files, making the architecture ideal for projecting situatitional off-ship to institute or cloud-based servers over low-bandwidth connections.

![Configuration](/docs/OVDM_Config_Main.png)

OpenVDM includes a hooks architure whereby vessel operators can link custom processes to run at key milestones during a cruise such as the start/end of a cruise, after a specific data transfer or after a data processing plugin completes.  The allow vessels operators to design and deploy potentially very sophisticated and asynchronous data processing workflows.

OpenVDM includes full RESTful API, allowing vessel operators to build their own custom web-based and stand-alone applications that leverage information stored within OpenVDM for their own, vessel-specific needs.

![Data Dashboard](/docs/OVDM_DataDashboard_Main.png)

#### Demo Site ####
<http://openvdm.oceandatarat.org>
- Username: ***admin***
- Password: ***demo***

## How it works

![Shipboard Dataflow](/docs/Shipboard_Dataflow.png)

1. The vessel operator tells OpenVDM where the data files live on the ship's network and howto connect to it (Direct connection, Samba, Rsync or SSH).
2. The vessel operator defines which remote data files to pull (include/exclude filters)
3. The vessel operator defines how pulled data files should be organized within the cruise directory on the OpenVDM Server
4. At the start of a cruise the vessel operator sets the cruise ID and start/stop dates.
5. Finally the operators sets the System Status to "On" and ***SHAZAAM!!!***... OpenVDM starts pulling in data files and organizing per the vessel operator's specification.

As the data files roll in, OpenVDM ensures the crew and shipboard science party have immediate, safe and read-only access via http and Samba share.  This workflow reduces the workload for marine techicians and improves access for the science party. (No more waking up techs in the middle of the night to get scientists their data!!!)

If the technician has setup backup locations for the data, OpenVDM use that information to continuously sync the cruise data directory with the backup locations.  Continuously sync'ing the cruise data directory to its backup locations reduces the time/work needed to provide data copies for scientists and archival facities.

### Want to get data to folks back on the beach??? (Read: TELEPRESENCE!!) ###
OpenVDM includes provisions for sending user-defined subsets of the cruise data directory to a shore-based server.  These ship-to-shore transfers include a priority ranking that help ensure mission-critical data/information are pushed to shore in a timely manner and not "stuck" behind lower-priorty files.  Defining new dataset to send to shore is as simple as filling out a form within the OpenVDM web-interface and clicking the "On" button.

## Installation ##

For installation instruction please read the [INSTALL.md](INSTALL.md) file located in this repository.

## Supporting the development effort ##

Want to join in the fun?  Please join the [#openvdm](https://oceandatarat.slack.com) Slack channel!  You'll need an invite so please send a email request to oceandatarat at gmail dot com. Once in the channel please introduce yourself and let us know how you're using OpenVDM and how you'd like to contribute to the project.

## Vessels Currently using OpenVDM ##
- *[R/V Endeavor](https://techserv.gso.uri.edu/)* (URI Graduate School of Oceanography)
- *[R/V Falkor](https://schmidtocean.org/rv-falkor/)* (Schmidt Ocean Institute)
- *[R/V Annie](http://engineeringfordiscovery.org/technology/rv-annie/)* (Global Foundation for Ocean Exploration)
- *[R/V Atlantic Explorer](http://www.bios.edu/research/facilities/atlantic-explorer/)* (Bermuda Institute of Ocean Sciences)
- *[R/V Helmer Hanssen](https://en.uit.no/om/enhet/artikkel?p_document_id=151541&p_dimension_id=88172&men=42374)* (UiT The Arctic University of Norway)
- *[R/V OceanXplorer1](http://www.oceanx.org/oceanxplorer/)* (OceanX)

## Vehicles Currently using OpenVDM ##
- *[ROV Subastian](https://schmidtocean.org/technology/robotic-platforms/4500-m-remotely-operated-vehicle-rov/)* (Schmidt Ocean Institute)
- *[ROV Yogi](https://www.engineeringfordiscovery.org/technology/rov-yogi/)* (Global Foundation for Ocean Exploration)
- *[ROV Chimaera, HOV Nadir, HOV Neptune](https://oceanx.org/oceanxplorer/deep-sea-vehicles)* (OceanX)

## Thanks and acknowledgments ##

OpenVDM is possible thanks to the generosity of the Schmidt Ocean Institute (SOI) who have continuously supported the project's development since 2012.

Thanks also to the marine technicians from the *R/V Falkor*, *R/V Endeavor*, *R/V Atlantic Explorer* and *R/V OceanXplorer1* for their patience during the early days of development and their continued support and enthusiasm for this project.
