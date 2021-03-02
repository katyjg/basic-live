/* Display modes from API resource
/* Can only be used via AJAX request if Access-Control-Allow-Origin header added to api resource
(function ($) {
    $.fn.displayModes = function (options) {
        let parent = $(this);
        let settings = $.extend({
            detailed: parent.data('detailed'),
            prefix: parent.data('prefix') || 'bt',
            root_id: parent.data('pk'),
            on_complete: function() {
            },
        }, options);

        let url = parent.data('modes-url');
        // fetch data and render
        $.ajax({
            dataType: 'json',
            url: url,
            success: function (data, status, xhr) {
                let width = parent.width();
                let height = width * (data.height || 1);
                let svg_id = settings.prefix + '-' + data.id;
                console.log(data);


                // run complete function
                settings.on_complete();
            }
        });
    }
}(jQuery));
*/

/* Display currently scheduled beamtime from API resource */
(function ($) {
    $.fn.displayBeamtime = function (options) {
        let parent = $(this);
        let settings = $.extend({
            detailed: parent.data('detailed'),
            prefix: parent.data('prefix') || 'bt',
            root_id: parent.data('pk'),
            on_complete: function() {
            },
        }, options);

        let url = parent.data('beamtime-url');
        let data = {};
        if (settings.detailed) { data['detailed'] = settings.detailed; }
        // fetch data and render
        $.ajax({
            dataType: 'json',
            url: url,
            data: data,
            success: function (data, status, xhr) {
                $.each(data, function(i, bt) {
                    $.each(bt.starts, function(j, st) {
                        let el = parent.find('[data-shift-id="' + st + '"]').find('[data-beamline="' + bt.beamline + '"]');
                        el.html(bt.title)
                          .addClass('full' + ' ' + bt.css_class)
                          .css('cursor', 'default');
                    });
                });

                // run complete function
                settings.on_complete();
            }
        });
    }
}(jQuery));

/* Display downtime from API resource */
(function ($) {
    $.fn.displayDowntime = function (options) {
        let parent = $(this);
        let settings = $.extend({
            on_complete: function() {
            },
        }, options);

        let url = parent.data('downtime-url');
        // fetch data and render
        $.ajax({
            dataType: 'json',
            url: url,
            success: function (data, status, xhr) {
                $.each(data, function(i, bt) {
                    $.each(bt.starts, function(j, st) {
                        parent.find('[data-shift-id="' + st + '"]').find('[data-beamline="' + bt.beamline + '"]')
                            .addClass('downtime').addClass(bt.style).attr('data-edit-link', bt.url);
                    });
                });

                // run complete function
                settings.on_complete();
            }
        });
    }
}(jQuery));


function freshEditor(sel) {
    $(sel).find('.block').removeClass('block');
    $(sel).find('.hold').removeClass('hold');
    $(sel + ' [data-beamline]:not(.full)').css('cursor', 'nw-resize');
    $(sel + ' [data-beamline].full').css('cursor', 'default');
}

function setupDowntimeEditor(sel, tog) {
    $(tog).on('change', function () {
        freshEditor(sel);
        if($(tog).prop('checked')) {
            $(sel + ' [data-beamline]').css('cursor', 'nw-resize');
            $(sel + ' .downtime').css('cursor', 'pointer');
            // Handle data-link, data-form-link and data-href
            $('.downtime').on('click', '[data-edit-link]', function () {

            });
        } else {
            $('.downtime').on('click');
        }
    });
}

function setupEditor(sel, sw) {

    let beamtime_url = $(sel).data('beamtime-url');
    let downtime_url = $(sel).data('downtime-url');

    $(sel + ' [data-beamline]')
        .css('cursor', 'nw-resize')
        .mouseover(function(event) {
            if ($('.hold').length && !$(this).hasClass('block')) {
                let row = $(this).closest('tr');
                row.prevAll().find('[data-beamline="' + $(this).data('beamline') + '"]').addClass('selected');
            }
        })
        .mouseout(function(event) {
            $('.selected').removeClass('selected');
        })
        .click(function (event) {
            let row = $(this).closest('tr');
            let dt = $(sw).prop('checked');

            if (dt && $(this).hasClass('downtime')) {
                $('#modal-target').asyncForm({url: $(this).data('edit-link')});
            } else {
                if (!$(this).hasClass('block')) {
                    // Check that the time slot is selectable

                    if (!$('.hold').length) {
                        // Starting time slot is selected

                        if (!$(this).hasClass('full') || dt) {
                            $(this).toggleClass('hold');
                            row.prevAll().find('td').addClass('block');
                            $('[data-beamline]').not('[data-beamline="' + $(this).data('beamline') + '"]').addClass('block');
                            $('[data-beamline]').not('.block').css('cursor', 'se-resize');
                        }

                    } else {
                        // Ending time slot is selected

                        let bl = $('.hold').data('beamline');
                        let start = $('.hold').closest('tr').data('shift-id');
                        let end = row.data('shift-id');
                        let url = beamtime_url + '&start=' + start + '&end=' + end + '&beamline=' + bl;
                        if (dt) {
                            url = downtime_url + '&start=' + start + '&end=' + end + '&beamline=' + bl;
                        }
                        $('#modal-target')
                            .on('hidden.bs.modal', function () {
                                freshEditor(sel);
                            }).asyncForm({
                            url: url,
                            complete: function (data) {
                                $.ajax({
                                    url: $(sel).data('week-url'),
                                    context: document.body,
                                    success: function (d) {
                                        window.location.href = window.location.pathname + "?start=" + start;
                                    }
                                });
                            }
                        });
                    }
                } else {
                    freshEditor(sel);
                }
            }
        });
}
