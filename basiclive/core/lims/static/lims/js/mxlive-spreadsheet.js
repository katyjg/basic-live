function getUrlParameter(sParam) {
    var sPageURL = window.location.search.substring(1),
        sURLVariables = sPageURL.split('&'),
        sParameterName,
        i;

    for (i = 0; i < sURLVariables.length; i++) {
        sParameterName = sURLVariables[i].split('=');

        if (sParameterName[0] === sParam) {
            return sParameterName[1] === undefined ? true : decodeURIComponent(sParameterName[1]);
        }
    }
}


function initSampleSpreadsheet() {
    let spreadsheet = $('#container-spreadsheet');

    function check_dupes(field) {
        let values = [];
        $("[data-field='" + field + "']").each(function(){    // get existing values
            let value = $(this).text();
            if ((value) && values.includes(value)) {
                $(this).addClass('error');
            } else {
                $(this).removeClass('error');
            }
            values.push(value);
        });
    }
    spreadsheet.on('paste', "[contenteditable='true']", function(e) {
        e.preventDefault();
        e.stopPropagation();
        let field_name = $(this).data('field');
        let selector = '[data-field="'+ field_name + '"]';
        let unique = Boolean($(this).data('unique'));
        let lines = strip(e.originalEvent.clipboardData.getData('Text')).split(/\r?\n/);    // clipboard rows

        let parent = $(this).parent();
        let position = parent.index();
        parent.nextAll().addBack().each(function(i, row){
            let value = slugify(lines[i]);
            let field = $(row).find(selector);
            let index = position + i;
            // check for unique values and flag accordingly
            if (unique) {
                check_dupes(field_name)
            }
            field.html(value);
        });
    });
    spreadsheet.on('click', 'a.remove-sample.remove', function(){
        // Safe remove
        $(this).removeClass('remove text-danger');
        $(this).popover('dispose');
        let parent = $(this).closest('tr');
        parent.find('[data-field]').each(function(){
            let field_name = $(this).data('field');
            $(this).html('');
            if ($(this).data('unique')) {
                check_dupes(field_name);
            }
        });
    });
    spreadsheet.on('click', 'a.remove-sample:not(.remove)', function(){
        // Prepare safe remove
        let btn = $(this);
        btn.addClass('remove text-danger');
        btn.popover({'content': 'click again to confirm'});
        btn.popover('show');
        setTimeout(function(){
            btn.removeClass('remove text-danger');
            btn.popover('dispose');
        }, 3000)
    });

    spreadsheet.on('keyup', "[contenteditable='true']", function(e) {
        // check for duplicates every time the value changes
        let field_name = $(this).data('field');
        if ($(this).data('unique')) {
            check_dupes(field_name);
        }
    });

    $('#save-spreadsheet').click(function(){
        let samples = [];
        let btn = $(this);
        btn.html('<i class="ti ti-reload spin"></i>');
        $('tr[data-location]').each(function(){
            let info = {};
            info['location'] = $(this).data('location');
            if ($(this).data('sample')) info['sample'] = $(this).data('sample');
            $(this).find('[data-field]').each(function(){
                info[$(this).data('field')] = strip($(this).text());
            });
            samples.push(info);
        });

        console.log(samples);

        $.ajax({
            type: 'post',
            dataType: "json",
            url: btn.data('post-action'),
            data: {'samples': JSON.stringify(samples)},
            beforeSend: function (xhr, settings) {
                xhr.setRequestHeader("X-CSRFToken", $.cookie('csrftoken'));
            },
            success: function (data, status, xhr) {
                if (data.url) {
                    window.location.replace(data.url);
                } else {
                    window.location.reload();
                }
            },
            error: function () {
                btn.shake();
                btn.html('<i class="ti ti-alert"></i>');
            }
        });
    });
}