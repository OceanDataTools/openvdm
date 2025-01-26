$(function () {
    'use strict';
    
    function updateCollectionSystemTransferStatus() {
        var getJobsURL = siteRoot + 'api/collectionSystemTransfers/getCollectionSystemTransfersStatuses';
        $.getJSON(getJobsURL, function (data, status) {
            if (status === 'success' && data !== null) {

                var output = '';
                var href = '';
                var i;
                
                for (i = 0; i < data.length; i++) {
                    if (data[i].status === "1") {
                        output = 'Stop';
                        href = siteRoot + 'config/collectionSystemTransfers/stop/' + data[i].collectionSystemTransferID;
                    } else {
                        output = 'Run';
                        href = siteRoot + 'config/collectionSystemTransfers/run/' + data[i].collectionSystemTransferID;
                    }
                    
                    $('#runStop' + data[i].collectionSystemTransferID).attr("href", href);
                    $('#runStop' + data[i].collectionSystemTransferID).html(output);

                }
            }
        });
    }
    
    setInterval(function () {
        updateCollectionSystemTransferStatus();
    }, 5000);

    $('#testResultsModal').on('hidden.bs.modal', function () {
        window.location.replace(siteRoot + 'config/collectionSystemTransfers');
    });

    var options = {
        valueNames: [ 'name' ]
    };

    var userList = new List('transfers', options);

    function interceptLinksToCurrentPage() {
        // Get the current page's base URL (excluding query strings, fragments)
        const currentUrl = window.location.href.split('#')[0].split('?')[0];

        // Get all <a> tags on the page
        const links = document.querySelectorAll('a');

        // Loop through each link and add an event listener for 'click'
        links.forEach(function(link) {
            // Check if the link's href is the same as the current page's URL (ignoring query params and fragments)
            const linkUrl = link.href.split('#')[0].split('?')[0];

            // If the link's URL is the same as the current page's URL, intercept it
            if (linkUrl === currentUrl) {
                link.addEventListener('click', function(event) {
                    // Prevent the default action (which is following the link)
                    event.preventDefault();

                    // Additional action: Log something or perform any custom logic
                    console.log('Intercepted link to the current page: ', link.href);

                    // You can perform any custom action here
                    // For example, let's simulate a page scroll, or open a modal, etc.

                    // Optionally, if you still want to navigate after your action, use:
                    window.location.href = link.href;  // to follow the link
                });
            }
        });
    }

    // Call the function to intercept links to the current page
    interceptLinksToCurrentPage();

});
