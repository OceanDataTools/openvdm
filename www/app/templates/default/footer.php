<?php

use Helpers\Assets;
use Helpers\Url;
use Helpers\Hooks;

//initialise hooks
$hooks = Hooks::get();

?>
    </div> <!-- page-wrapper -->
    <span class="text-muted pull-right" style="padding: 15px"><a href="https://github.com/oceandatatools/openvdm" target="_blank">OpenVDM</a> is licensed under the <a href="http://www.gnu.org/licenses/MIT">MIT</a> public license</span>
</div> <!-- wrapper -->


<!-- JS -->    
<script type="text/javascript">
    var siteRoot = "<?php echo DIR; ?>";
    
    var lowering_name = "<?php echo LOWERING_NAME; ?>";
    var cruise_name = "<?php echo CRUISE_NAME; ?>";
    
    <?php echo (isset($data['cruiseID']) ? 'var cruiseID = "' . $data['cruiseID'] . '";' : ''); ?>
    
    <?php echo (isset($data['dataWarehouseApacheDir']) ? 'var cruiseDataDir = "' . $data['dataWarehouseApacheDir'] . '";' : ''); ?>
    
    <?php echo (isset($data['geoJSONTypes']) ? 'var geoJSONTypes = [\'' . join('\', \'', $data['geoJSONTypes']) . '\'];' : ''); ?>
    
    <?php echo (isset($data['tmsTypes']) ? 'var tmsTypes = [\'' . join('\', \'', $data['tmsTypes']) . '\'];' : ''); ?>
    
    <?php echo (isset($data['jsonTypes']) ? 'var jsonTypes = [\'' . join('\', \'', $data['jsonTypes']) . '\'];' : ''); ?>

    <?php echo (isset($data['jsonReversedYTypes']) ? 'var jsonReversedYTypes = [\'' . join('\', \'', $data['jsonReversedYTypes']) . '\'];' : ''); ?>

    <?php echo (isset($data['jsonReversedYInvertedTypes']) ? 'var jsonReversedYInvertedTypes = [\'' . join('\', \'', $data['jsonReversedYInvertedTypes']) . '\'];' : ''); ?>

    <?php echo (isset($data['jsonInvertedTypes']) ? 'var jsonInvertedTypes = [\'' . join('\', \'', $data['jsonInvertedTypes']) . '\'];' : ''); ?>

<?php
    if(isset($data['subPages'])) {
        echo '    var subPages = [];' . "\n";
        
        foreach ($data['subPages'] as $key => $subPage) {
            echo '    subPages[\'' . $key . '\'] = \'' . $subPage . '\';' . "\n";
            
        }
    }
?>
    
</script>

<?php 

$jsFileArray = array(
    DIR . 'node_modules/jquery/dist/jquery.min.js',
    DIR . 'node_modules/bootstrap/dist/js/bootstrap.min.js',
    DIR . 'node_modules/metismenu/dist/metisMenu.min.js',
    DIR . 'node_modules/js-cookie/src/js.cookie.js',
    DIR . 'node_modules/list.js/dist/list.min.js',    
    Url::templatePath() . 'js/sb-admin-2.js',
    Url::templatePath() . 'js/header.js',    
    Url::templatePath() . 'js/modals.js',
);
    
if (isset($data['javascript'])){
    foreach ($data['javascript'] as &$jsFile) {
        if ($jsFile === 'leaflet') {
            array_push($jsFileArray, DIR . 'node_modules/leaflet/dist/leaflet.js');
            array_push($jsFileArray, DIR . 'node_modules/leaflet-fullscreen/dist/Leaflet.fullscreen.min.js');
            array_push($jsFileArray, DIR . 'node_modules/leaflet-easyprint/dist/bundle.js');
        } else if ($jsFile === 'leaflet-timedimension') {
            array_push($jsFileArray, DIR . 'node_modules/leaflet-timedimension/dist/leaflet.timedimension.min.js');
        } else if ($jsFile === 'charts') {
            array_push($jsFileArray, Url::templatePath() . "js/chartColors.js");
            array_push($jsFileArray, DIR . 'node_modules/chart.js/dist/chart.min.js');
            array_push($jsFileArray, DIR . 'node_modules/luxon/build/global/luxon.min.js');
            array_push($jsFileArray, DIR . 'node_modules/chartjs-adapter-luxon/dist/chartjs-adapter-luxon.umd.min.js');
        } else if ($jsFile === 'charts-zoom') {
            array_push($jsFileArray, DIR . 'node_modules/hammerjs/hammer.min.js');
            array_push($jsFileArray, DIR . 'node_modules/chartjs-plugin-zoom/dist/chartjs-plugin-zoom.min.js');
        } else if ($jsFile === 'datetimepicker') {
            array_push($jsFileArray, DIR . 'node_modules/moment/moment.js');
            array_push($jsFileArray, DIR . 'node_modules/eonasdan-bootstrap-datetimepicker/build/js/bootstrap-datetimepicker.min.js');   
            array_push($jsFileArray, Url::templatePath() . 'js/datetimepicker.js');
        } else {
            array_push($jsFileArray, Url::templatePath() . 'js/' . $jsFile . '.js');
        }
    }
}

Assets::js($jsFileArray);

//hook for plugging in javascript
$hooks->run('js');

//hook for plugging in code into the footer
$hooks->run('footer');

?>

</body>
</html>
