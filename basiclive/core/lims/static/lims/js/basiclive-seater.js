    function initSampleSeater() {
        const colorScale = d3.scaleOrdinal(d3.schemeSet1);
        $('.seat-container').each(function () {
            $(this).layoutContainer({
                detailed: true,
                labelled: true,
                loadable: false,
                prefix: 'sscnt',
                on_complete: function() {  // color samples by group in #sample-seater
                    $('#sample-seater svg.sample.occupied')
                        .removeClass('occupied')
                        .each(function(){
                            let group = $('.group-selector[data-group="' + $(this).data('group') + '"]').data();
                            $(this).find('> .envelope').attr('fill', colorScale(group.selector));
                        });
                }
            });

        });

        d3.selectAll('.group-chooser [data-selector]')
            .style('color', 'black')
            .style('background-color', function () {
                return colorScale($(this).data('selector'));
            }).on('click', function () {
                let remove = (!$(this).hasClass('selected'));
                let group = $(this).data('group');
                $('.group-selector.selected').removeClass('selected');
                $(this).toggleClass('selected', remove);
                $('.input-group #group-' + group).toggleClass('selected', remove);
            });

        $(document).on('click', '#sample-seater svg.sample', function () {
            let group = $('.group-selector.selected').data();
            if (group) {
                if ($(this).hasClass('empty')) {
                    $(this).removeClass('empty')
                        .attr('data-group', group.group)
                        .find(' > .envelope').attr('fill', colorScale(group.selector));
                } else {
                    $(this).addClass('empty')
                        .removeAttr('data-group')
                        .removeData('group');
                }
            }
        });
        $('.seater .badge[data-pk]').hover(
            function () { //enter
                let group = $('.group-selector.selected').data();
                if (group) {
                    $(this).css('background-color', colorScale(group.selector));
                }
            },
            function () { //exit
                let group = $('.group-selector.selected').data();
                if (group) {
                    $(this).css('background-color', '');
                }
            }
        ).click(function () {
            let group = $('.group-selector.selected').data();
            if (group) {
                let pins = $('#seats-for-' + $(this).data('pk') + ' svg.sample');
                let to_add = pins.filter('.empty');
                let to_del = pins.filter('[data-group='+group.group+']');
                if (to_add.length > 0) {
                    to_add.removeClass('empty')
                        .attr('data-group', group.group)
                        .find('> .envelope').attr('fill', colorScale(group.selector));
                } else {
                    to_del.addClass('empty')
                        .removeAttr('data-group')
                        .removeData('group');
                }
            }
        });
        $('#save-seats').click(function(){
            let info = [];
            let btn = $(this);
            btn.html('<i class="ti ti-reload spin"></i>');
            $('.seat-container').each(function(){
                let cid = $(this).data('pk');
                $(this).find('svg.sample[data-group]').each(function(){
                    info.push({
                        group: $(this).data('group'),
                        container: cid,
                        location: $(this).data('loc'),
                    })
                })
            });
            $('input.free-container').each(function() {
                let input = $(this);
                for(i=0; i<input.val(); i++) {
                    info.push({
                        group: input.data('group'),
                        container: input.data('container'),
                        location: null
                    })
                }
            });

            $.ajax({
                type: 'post',
                dataType: "json",
                url: btn.data('post-action'),
                data: {'samples': JSON.stringify(info)},
                beforeSend: function (xhr, settings) {
                    xhr.setRequestHeader("X-CSRFToken", $.cookie('csrftoken'));
                    console.log(info);
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