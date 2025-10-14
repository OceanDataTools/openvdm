$(function () {
    'use strict';

    function updateCruiseDataTransferStatus() {
        var getCruiseDataTransferStatusURL = siteRoot + 'api/cruiseDataTransfers/getCruiseDataTransfersStatuses';
        $.getJSON(getCruiseDataTransferStatusURL, function (data, status) {
            if (status === 'success' && data !== null) {

                var output = '';
                var href = '';
                var i;

                for (i = 0; i < data.length; i++) {
                    if (data[i].status === "1") {
                        output = 'Stop';
                        href = siteRoot + 'config/cruiseDataTransfers/stop/' + data[i].cruiseDataTransferID;
                        $('#runStop' + data[i].cruiseDataTransferID).removeClass("text-muted");
                    } else if (data[i].status === "5") {
                        output = 'Stopping';
                        href = '#';
                        $('#runStop' + data[i].cruiseDataTransferID).addClass("text-muted");
                        $('#runStop' + data[i].cruiseDataTransferID).attr("disabled", "disabled");
                    } else if (data[i].status === "6") {
                        output = 'Starting';
                        href = '#';
                        $('#runStop' + data[i].cruiseDataTransferID).addClass("text-muted");
                        $('#runStop' + data[i].cruiseDataTransferID).attr("disabled", "disabled");
                    } else {
                        output = 'Run';
                        href = siteRoot + 'config/cruiseDataTransfers/run/' + data[i].cruiseDataTransferID;
                        $('#runStop' + data[i].cruiseDataTransferID).removeClass("text-muted");
                    }

                    $('#runStop' + data[i].cruiseDataTransferID).attr("href", href);
                    $('#runStop' + data[i].cruiseDataTransferID).html(output);

                    if (data[i].status === "3") {
                        $('#testFail' + data[i].cruiseDataTransferID).html('<i class="fa fa-warning text-danger"></i>');
                    } else {
                        $('#testFail' + data[i].cruiseDataTransferID).html('');
                    }
                }
            }
        });
    }

    setInterval(function () {
        updateCruiseDataTransferStatus();
    }, 5000);

    var options = {
        valueNames: [ 'name' ]
    };

    var transferList = new List('transfers', options);

    function interceptLinksToCurrentPage() {
        // Get the current URL's path (ignoring query strings and fragments)
        const currentPath = window.location.pathname.split('?')[0].split('#')[0];

        // Get all <a> tags on the page
        const links = document.querySelectorAll('a');

        // Loop through each link and add an event listener for 'click'
        links.forEach(function(link) {
            // Check if the link's href starts with the same path as the current page's path
            const linkPath = new URL(link.href).pathname.split('?')[0].split('#')[0];
            const fragment = new URL(link.href).hash

            // If the link's path starts with the same base path, intercept it
            if (linkPath.startsWith(currentPath) && !fragment) {
                link.addEventListener('click', function(event) {
                    // Prevent the default action (which is following the link)
                    event.preventDefault();

                    // Additional action: Log something or perform any custom logic
                    // console.log('Intercepted link to the current or related page: ', link.href);

                    // Get the value of the input field (replace 'input-field' with your actual input's ID or selector)
                    const inputField = document.getElementById('transfer-filter'); // Example: <input id="input-field" />
                    inputField.blur();
                    const inputValue = inputField ? inputField.value : ''; // Get input field value or empty if not found

                    // Add the input field value as a query parameter to the URL
                    const url = new URL(link.href);
                    if (inputValue) {
                        // Append the input value as a query parameter (e.g., ?input=value)
                        url.searchParams.set('filter', inputValue);
                    }
                    else {
                        url.searchParams.delete('filter')
                    }

                    // Log the new URL (for demonstration purposes)
                    // console.log('New URL with input value:', url.href);

                    // You can perform any custom action here
                    // For example, let's simulate a page scroll, or show a modal, etc.

                    // Optionally, if you still want to navigate after your action, use:
                    window.location.href = url.href;  // to follow the link
                });
            }
        });
    }

    // Call the function to intercept links to the current or related pages
    interceptLinksToCurrentPage();

    // Filter list
    const inputField = document.getElementById('transfer-filter');
    const inputValue = inputField ? inputField.value : '';
    transferList.search(inputValue);

});
