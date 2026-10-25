<?php
/*
 * File Naming Guide (#451): what each collection system's files must be
 * called to be transferred, from its filters (Helpers\FileNamingGuide).
 * Laid out to print: the navigation, sidebar and buttons are left out.
 */

$h = function ($text) {
    return htmlspecialchars((string) $text, ENT_QUOTES, 'UTF-8');
};

// One pattern's explanation: its pieces in order, an example, a warning
$explain = function ($described) use ($h) {
    $pieces = array();
    foreach ($described['sentence'] as list($kind, $text)) {
        $pieces[] = $kind === 'code' ? '<code>' . $h($text) . '</code>' : $h($text);
    }
    $html = '<li><code>' . $h($described['pattern']) . '</code>';
    if ($described['filled'] !== $described['pattern']) {
        $html .= ' (now <code>' . $h($described['filled']) . '</code>)';
    }
    $html .= ': ' . implode('', $pieces);
    if ($described['example'] !== '') {
        $html .= ', e.g. <code>' . $h($described['example']) . '</code>';
    }
    if ($described['warning'] !== '') {
        $html .= '<br><span class="text-danger"><i class="fa fa-warning"></i> ' . $h($described['warning']) . '</span>';
    }
    return $html . '</li>';
};
?>
<style>
    .naming-guide-section { margin-bottom: 24px; }
    .naming-guide-section h3 { margin-top: 0; }
    .naming-guide-section h4 { margin: 14px 0 6px; font-size: 15px; }
    .naming-guide-section ul { padding-left: 20px; margin-bottom: 6px; }
    .naming-guide-description { margin-bottom: 10px; }
    .naming-guide-description p, .naming-guide-description ul, .naming-guide-description ol { margin-bottom: 6px; }
    .naming-guide-description h1, .naming-guide-description h2, .naming-guide-description h3,
    .naming-guide-description h4, .naming-guide-description h5, .naming-guide-description h6 { font-size: 14px; font-weight: bold; margin: 8px 0 4px; }
    @media print {
        .navbar, .sidebar, .no-print { display: none !important; }
        #page-wrapper { margin: 0 !important; border: none !important; padding: 0 !important; }
        .naming-guide-section { page-break-inside: avoid; break-inside: avoid; }
        .panel { border: none !important; box-shadow: none !important; }
        a[href]:after { content: none !important; }
        code { border: none; background: none; padding: 0; color: #000; }
    }
</style>

<div class="row">
    <div class="col-lg-12">
        <h1 class="page-header">File Naming Guide</h1>
        <p>
            What each collection system's files must be called for OpenVDM to copy them into the
            <?php echo $h(strtolower(CRUISE_NAME)); ?> data, from the transfers' filters as they are now
            (<?php echo $h(CRUISE_NAME); ?> <code><?php echo $h($data['context']['cruiseID']); ?></code><?php
            if ($data['context']['loweringID'] !== '') { ?>, <?php echo $h(LOWERING_NAME); ?> <code><?php echo $h($data['context']['loweringID']); ?></code><?php } ?>,
            <?php echo $h(gmdate('Y/m/d H:i', $data['context']['now'])); ?> UTC).
        </p>
        <?php echo \Helpers\Markdown::alert(); ?>
        <p class="no-print">
            <button type="button" class="btn btn-sm btn-primary" onclick="window.print()"><i class="fa fa-print"></i> Print</button>
<?php if ($data['onlyID']) { ?>
            <a class="btn btn-sm btn-default" href="<?php echo DIR; ?>config/collectionSystemTransfers/fileNamingGuide">All transfers</a>
<?php } elseif ($data['showAll']) { ?>
            <a class="btn btn-sm btn-default" href="<?php echo DIR; ?>config/collectionSystemTransfers/fileNamingGuide">Enabled transfers only</a>
<?php } else { ?>
            <a class="btn btn-sm btn-default" href="<?php echo DIR; ?>config/collectionSystemTransfers/fileNamingGuide?all=1">Include disabled transfers</a>
<?php } ?>
            <a class="btn btn-sm btn-default" href="<?php echo DIR; ?>config/collectionSystemTransfers">Back to Collection System Transfers</a>
        </p>
    </div>
</div>

<div class="row">
    <div class="col-lg-12">
<?php if (!$data['guides']) { ?>
        <p>There are no <?php echo $data['showAll'] || $data['onlyID'] ? '' : 'enabled '; ?>collection system transfers to show.</p>
<?php } ?>
<?php foreach ($data['guides'] as $guide) { ?>
        <div class="panel panel-default naming-guide-section">
            <div class="panel-body">
                <h3>
                    <?php echo $h($guide['longName']); ?>
                    <small><?php echo $h($guide['name']); ?> &middot; <?php echo $h($guide['lowering'] ? LOWERING_NAME . '-level' : CRUISE_NAME . '-level'); ?><?php echo $guide['enabled'] ? '' : ' &middot; disabled'; ?></small>
                    <?php if (!$data['onlyID']) { ?><a class="btn btn-xs btn-default pull-right no-print" href="<?php echo DIR; ?>config/collectionSystemTransfers/fileNamingGuide?id=<?php echo $guide['id']; ?>">This one only</a><?php } ?>
                </h3>
<?php if ($guide['description'] !== '') { ?>
                <div class="naming-guide-description"><?php echo \Helpers\Markdown::render($guide['description']); ?></div>
<?php } ?>
                <p>
                    <strong>Collected from:</strong> <?php echo $h($guide['typeName']); ?><?php
                    foreach ($guide['source'] as $label => $value) { ?>, <?php echo $h(strtolower($label)); ?> <code><?php echo $h($value); ?></code><?php } ?>
                </p>

                <h4>Copied: files matching any of</h4>
<?php if ($guide['include']) { ?>
                <ul><?php foreach ($guide['include'] as $described) { echo $explain($described); } ?></ul>
<?php } else { ?>
                <p class="text-danger">No Include patterns, so no files are copied.</p>
<?php } ?>

                <h4>Not copied, and listed under Filename Errors on OpenVDM's main page</h4>
                <ul>
<?php foreach ($guide['exclude'] as $described) { echo $explain($described); } ?>
                    <li>any other file that doesn't match a pattern under <em>Copied</em></li>
                </ul>

<?php if ($guide['ignore']) { ?>
                <h4>Skipped without being reported</h4>
                <ul><?php foreach ($guide['ignore'] as $described) { echo $explain($described); } ?></ul>
<?php } ?>

                <h4>Also</h4>
                <ul>
<?php foreach ($guide['rules'] as $rule) { ?>
                    <li><?php echo $h($rule); ?></li>
<?php } ?>
                </ul>
            </div>
        </div>
<?php } ?>

        <div class="panel panel-default naming-guide-section">
            <div class="panel-body">
                <h3>Placeholders</h3>
                <p>Patterns may use these; OpenVDM fills them in before checking a file's name.</p>
                <table class="table table-condensed">
                    <thead><tr><th>Placeholder</th><th>Matches</th><th>Now</th></tr></thead>
                    <tbody>
<?php foreach ($data['placeholders'] as list($placeholder, $meaning, $value)) { ?>
                        <tr><td><code><?php echo $h($placeholder); ?></code></td><td><?php echo $h($meaning); ?></td><td><?php echo $value !== '' ? '<code>' . $h($value) . '</code>' : ''; ?></td></tr>
<?php } ?>
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</div>
