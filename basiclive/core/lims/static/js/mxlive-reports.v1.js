function rounded(v) {
    var exp = Math.pow(10, -Math.ceil(Math.log(Math.abs(v), 10)));
    return Math.round(v*exp)/exp;
}

function choose(choices) {
  var index = Math.floor(Math.random() * choices.length);
  return choices[index];
}

Array.cleanspace = function(a, b, steps){
    var A= [];

    steps = steps || 7;
    var min =  rounded((b - a)/8);
    a = Math.ceil(a/min)*min;
    b = Math.floor(b/min)*min;
    var step = Math.ceil(((b - a)/steps)/min)*min;

    A[0]= a;
    while(a+step<= b){
        A[A.length]= a+= step;
    }
    return A;
};

function inv_sqrt(a) {
    var A = [];
    for (var i=0; i < a.length; i++) {
        A[i] = Math.pow(a[i], -0.5);
    }
    return A;
}


// Live Reports from MxLIVE
function draw_pie_chart() {
    let color_scheme = d3.schemeSet2.concat(d3.schemeDark2);
    let colors = d3.scaleOrdinal( color_scheme);

    function chart(selection) {
        selection.each(function (data) {
            var margin = {out: 10, left: Math.max(10, 0.5*(width-height)), top: Math.max(10, 0.5*(height-width))};

            var svg = d3.select(this)
                .attr("viewBox", "0 0 " + width + " "+ height)
                //.attr("width", width)
                //.attr("height", height)
                .append("g")
                .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

            var radius = Math.min(width - 2*margin.left, height - 2*margin.top)/2.0;

            var arc = d3.arc()
                    .innerRadius((radius)*innerRadius)
                    .outerRadius(radius)
                    .startAngle(function(d, i) {
                        return deg2rad(data[i]['start']);
                    })
                    .endAngle(function(d, i) {
                        return deg2rad(data[i]['start'] + data[i]['value']);
                    });

            function deg2rad(deg) {
                return deg * Math.PI / 180;
            }


            function centerTranslation() {
                return 'translate('+radius +','+ radius +')';
            }

            var centerTx = centerTranslation();

            var arcs = svg.append('g')
                    .attr('class', 'arc')
                .attr('transform', centerTx);
            arcs.selectAll('path')
                    .data(data)
                    .enter().append('path')
                    .attr('fill', function(d, i) {
                        return data[i]['color'] || colors(i);
                    })
                    .attr('d', arc);

            var lg = svg.append('g')
                    .attr('class', 'axis-label')
                    .attr('transform', centerTx);

            var labels = [];
            $.each(data, function(i, d) {
                if (d['label']) {
                    labels.push(d['label']);
                }
            });

            if (labels.length > 1) {
                lg.selectAll('text')
                    .data(data)
                    .enter().append('text')
                    .attr('transform', function (d, i) {
                        var r = radius + margin.out;
                        var alpha = deg2rad((data[i]['value'] / 2) + data[i]['start'] - 90);
                        var x = r * Math.cos(alpha);
                        var y = r * Math.sin(alpha);
                        return 'translate(' + (x) + ',' + (y) + ')';
                    })
                    .text(function (d, i) {
                        return data[i]['label'];
                    })
                    .style("text-anchor", function (d, i) {
                        var r = radius + margin.out;
                        var alpha = deg2rad((data[i]['value'] / 2) + data[i]['start'] - 90);
                        var x = r * Math.cos(alpha);
                        if (x > 0) {
                            return 'start';
                        } else {
                            return 'end';
                        }
                    })
                    .attr('fill', function (d, i) {
                        return data[i]['color'] || colors(i);
                    });
            } else {
                lg.append('text').text(labels[0]).attr('class', 'text-large').attr('text-anchor', 'middle').attr('alignment-baseline', 'middle');
            }
        });
    }

    chart.width = function (value) {
        if (!arguments.length) return width;
        width = value;
        return chart;
    };

    chart.height = function (value) {
        if (!arguments.length) return height;
        height = value;
        return chart;
    };

    chart.innerRadius = function (value) {
        if (!arguments.length) return innerRadius;
        innerRadius = value;
        return chart;
    };

    return chart;
}

function drawStackChart(data, label, canvasStackChart, colorStackChart, xStackChart, yStackChart, heightStackChart) {

    colorStackChart.domain(d3.keys(data[0]).filter(function (key) { return key !== label && key !== 'color'; }));

    data.forEach(function (d) {
        var y0 = 0;
        d.ages = colorStackChart.domain().map(function (name) { return { name: name, y0: y0, y1: y0 += +d[name], color: d['color'] || null, label: d[label] }; });
        d.total = d.ages[d.ages.length - 1].y1;
    });

    xStackChart.domain(data.map(function (d) { return d[label]; }));
    yStackChart.domain([0, d3.max(data, function (d) { return d.total; })]);

    canvasStackChart.append("g")
        .attr("class", "x axis")
        .attr("transform", "translate(0," + heightStackChart + ")")
        .call(d3.axisBottom(xStackChart))
        .selectAll("text")
        .attr("y", 10)
        .attr("x", 0)
        .attr("dy", ".35em")
        .style("text-anchor", "middle");

    var state = canvasStackChart.selectAll("."+label+"")
        .data(data)
        .enter().append("g")
        .attr("class", "g")
        .attr("transform", function (d) { return "translate(" + xStackChart(d[label]) + ",0)"; });

    var active_link = "0";
    var legendClassArray = [];
    var legend = canvasStackChart.selectAll(".legend")
        .data(colorStackChart.domain().slice().reverse())
        .enter().append("g")
        .attr("class", function (d) {
            legendClassArray.push(d.replace(/\s/g, '')); //remove spaces
            return "legend";
        })
        .attr("transform", function(d, i) { return "translate(0," + i * 20 + ")"; });

    //reverse order to match order in which bars are stacked
    legendClassArray = legendClassArray.reverse();

    state.selectAll("rect")
        .data(function (d) { return d.ages; })
        .enter().append("rect")
        .attr("width", xStackChart.bandwidth())
        .attr("class", function(i, d) { return 'class' + legendClassArray[d]; })
        .attr("title", function(d, i) { return legendClassArray[i] + ' (' + d.label + '): ' + (d.y1 - d.y0);})
        .attr("y", function (d) { return yStackChart(d.y1); })
        .attr("height", function (d) { return yStackChart(d.y0) - yStackChart(d.y1); })
        .style("fill", function (d) { return d.color && d.color || colorStackChart(d.name); })
        .style("opacity", function (d, i) { return d.color && 1 - ((0.75/legendClassArray.length) * i) || 1});


    if (legendClassArray.length > 1) {
        legend.append("circle")
            .attr("cy", 9)
            .attr("r", 9)
            .style("fill", colorStackChart)
            .attr("id", function (d, i) {
                return "id" + d.replace(/\s/g, '');
            })
            .on("mouseover", function () {
                if (active_link === "0") d3.select(this).style("cursor", "pointer");
                else {
                    if (active_link.split("class").pop() === this.id.split("id").pop()) {
                        d3.select(this).style("cursor", "pointer");
                    } else d3.select(this).style("cursor", "auto");
                }
            })
            .on("click", function (d) {
                var active_id = '#id' + active_link;
                d3.select(active_id).style("stroke", "none");
                if (active_link !== this.id.split("id").pop()) {
                    if (active_link !== "0") {
                        restorePlot($(active_id)[0], duration = 0, delay = 0);
                    }
                    d3.select(this)
                        .style("stroke", "black")
                        .style("stroke-width", 2);

                    active_link = this.id.split("id").pop();
                    plotSingle(this);
                } else {
                    restorePlot($(active_id)[0], duration=500, delay=100);
                    active_link = "0";
                }
            });

        legend.append("text")
            .attr("x", 24)
            .attr("y", 9)
            .attr("dy", ".35em")
            .style("text-anchor", "start")
            .text(function (d) {
                return d;
            });
    }

    function restorePlot(d, duration=500, delay=100) {
        class_keep = d.id.split("id").pop();
        idx = legendClassArray.indexOf(class_keep);

        $.each(state.selectAll("rect"), function (i, e) {
            //get height and y posn of base bar and selected bar
            $.each(e, function(j, r) {
                if (r[idx]) {
                    d3.select(r[idx])
                        .transition()
                        .ease(d3.easeBounce)
                        .duration(duration)
                        .delay(delay)
                        .attr("y", y_orig[j])
                        .attr("height", h_orig[j]);
                }
            });
        });

        //restore opacity of erased bars
        for (i = 0; i < legendClassArray.length; i++) {
          if (legendClassArray[i] != class_keep) {
            state.selectAll(".class" + legendClassArray[i])
              .transition()
              .duration(duration)
              .delay(delay)
              .style('display', 'block');
          }
        }

    }

    function plotSingle(d) {
        let class_keep = d.id.split("id").pop();
        let idx = legendClassArray.indexOf(class_keep);
        let key_keep = class_keep;
        $.each(data[0], function(k) {
            if (k.replace(/\s/g, '') === class_keep) {
                key_keep = k;
                return false;
            }
        });
        let ySingleChart = d3.scaleLinear().range([heightStackChart, 0]).domain([0, d3.max(data, function (d) { return d[key_keep]; })]);

        for (i = 0; i < legendClassArray.length; i++) {
            if (legendClassArray[i] !== class_keep) {
                state.selectAll(".class" + legendClassArray[i])
                    .transition()
                    .duration(500)
                    .style("display", "none");
            }
        }

        let y_orig = [];
        let h_orig = [];
        $.each(state.selectAll("rect"), function (i, d) {
            //get height and y posn of base bar and selected bar

            $.each(d, function(j, r) {
                if (r[idx]) {
                    h_keep = d3.select(r[idx]).attr("height");
                    y_keep = d3.select(r[idx]).attr("y");
                    y_orig.push(y_keep);
                    h_orig.push(h_keep);

                    h_base = d3.select(r[0]).attr("height");
                    y_base = d3.select(r[0]).attr("y");

                    h_shift = h_keep - h_base;
                    y_new = y_base - h_shift;

                    d3.select(r[idx])
                        .transition()
                        .ease(d3.easeBounce)
                        .duration(500)
                        .delay(100)
                        .attr("y", function (d) { return heightStackChart - (ySingleChart(d.y0) - ySingleChart(d.y1)); })
                        .attr("height", function (d) { return ySingleChart(d.y0) - ySingleChart(d.y1);})
                        .call(yStackChart);
                }
            });

        });

    }
}

function draw_xy_chart() {

    function chart(selection) {
        selection.each(function (datasets) {
            var notes_labels = [];
            if (notes.length) {
                $.each(notes, function(i, note) {
                    if (note['label']) {
                        notes_labels.push(note['label']);
                    }
                })
            }
            var xoffset = notes_labels.length && 40 || 0;
            var bmargin = 20;
            if (xlabel) {
                bmargin = 50;
            }
            var margin = {top: 20, right: width * 0.15, bottom: bmargin, left: width * 0.15},
                innerwidth = width - margin.left - margin.right,
                innerheight = height - margin.top - margin.bottom;

            var svg = d3.select(this)
                .attr("viewBox", "0 0 "+ width + " " + height)
                .append("g")
                .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

            var color_scale = d3.scaleOrdinal(d3.schemeDark2);
            var y1data = [], y2data = [];
            var y1datasets = [], y2datasets = [];

            if (scatter === 'bar') {
                var color = datasets['color'];
                var xmin = xlimits[0] || d3.min(datasets.data);
                var xmax = xlimits[1] || d3.max(datasets.data);
                switch (xscale) {
                    case 'time':
                        var x_scale = d3.scaleTime()
                            .range([0, innerwidth])
                            .domain([xmin, xmax]);
                        break;
                    case 'linear':
                        var x_scale = d3.scaleLinear()
                            .range([0, innerwidth])
                            .domain([xmin, xmax]);
                        break;
                }
                var bins = d3.histogram()
                    .value(function (d) {
                        return d;
                    })
                    .domain([d3.min(datasets.data), d3.max(datasets.data)])
                    .thresholds(x_scale.ticks(binning))(datasets['data']);
                var y1_scale = d3.scaleLinear()
                    .domain([0, d3.max(bins, function (d) {
                        return d.length;
                    })])
                    .range([innerheight, 0]);
            } else {
                var xmin = xlimits[0] || d3.min(datasets, function (d) { return d3.min(d.x);});
                var xmax = xlimits[1] || d3.max(datasets, function (d) { return d3.max(d.x);});
                switch (xscale) {
                    case 'inv-square':

                        var x_scale = d3.scalePow().exponent(-2)
                            .range([0, innerwidth])
                            .domain([xmax, xmin]);
                        break;
                    case 'pow':
                        var x_scale = d3.scalePow()
                            .range([0, innerwidth])
                            .domain([xmin, xmax]);
                        break;
                    case 'log':
                        var x_scale = d3.scaleLog()
                            .range([0, innerwidth])
                            .domain([xmin, xmax]);
                        break;
                    case 'identity':
                        var x_scale = d3.scaleIdentity()
                            .range([0, innerwidth])
                            .domain([xmin, xmax]);
                        break;
                    case 'time':
                        var x_scale = d3.scaleTime()
                            .range([0, innerwidth])
                            .domain([xmin, xmax]);
                        break;
                    case 'linear':
                        var x_scale = d3.scaleLinear()
                            .range([0, innerwidth])
                            .domain([xmin, xmax]);
                        break;
                    case 'inverse':
                        var x_scale = d3.scaleLinear()
                            .range([0, innerwidth])
                            .domain([xmax, xmin]);
                }

                switch(interpolation) {
                    case 'cardinal':
                        var fit = d3.curveCardinal;
                        break;
                    case 'step':
                        var fit = d3.curveStep;
                        break;
                    case 'step-after':
                        var fit = d3.curveStepAfter;
                        break;
                    case 'step-before':
                        var fit = d3.curveStepBefore;
                        break;
                    case 'basis':
                        var fit = d3.curveBasis;
                        break;
                    case 'linear':
                        var fit = d3.curveLinear;
                }

                for (var p = 0; p < datasets.length; p++) {
                    datasets[p]['color'] = color_scale(p);
                    if ((datasets[p]['y1'])) {
                        y1data = y1data.concat(datasets[p]['y1']);
                        y1datasets.push(datasets[p]);
                    }
                    if ((datasets[p]['y2'])) {
                        y2data = y2data.concat(datasets[p]['y2']);
                        y2datasets.push(datasets[p]);
                    }
                }

                var y1_scale = d3.scaleLinear()
                    .range([innerheight - xoffset, 0])
                    .domain([y1limits[0] || d3.min(y1data),
                        y1limits[1] || d3.max(y1data)]);

                var y2_scale = d3.scaleLinear()
                    .range([innerheight - xoffset, 0])
                    .domain([y2limits[0] || d3.min(y2data),
                        y2limits[1] || d3.max(y2data)]);
            }


            var x_axis = d3.axisBottom()
                .scale(x_scale)
                .tickSize(-innerheight);
            if (xscale === 'inv-square') {
                var ticks = inv_sqrt(Array.cleanspace(Math.pow(xmax, -2), Math.pow(xmin, -2), 8));
                x_axis.tickValues(ticks).tickFormat(d3.format(".3"));
            } else if (xscale === 'time' && timeformat) {
                x_axis.ticks(7).tickFormat(d3.timeFormat(timeformat));
            }

            var y1_axis = d3.axisLeft()
                .scale(y1_scale)
                .tickSize(-innerwidth);

            var y2_axis = d3.axisRight()
                .scale(y2_scale);


            svg.append("g")
                .attr("class", "x axis")
                .attr("transform", "translate(0," + (innerheight) + ")")
                .call(x_axis);
            svg.append("text")
                .attr("transform", "translate(" + (innerwidth / 2) + "," + (height - margin.bottom / 2) + ")")
                .style("text-anchor", "middle")
                .text(xlabel);

            svg.append("g")
                .attr("class", "y axis")
                .call(y1_axis)
                .append("text")
                .attr("transform", "translate(0," + innerheight / 2 + "), rotate(-90)")
                .attr("y", 6)
                .attr("dy", "-3.5em")
                .style("text-anchor", "middle")
                .attr("fill", function (_, i) {
                    if (y1datasets.length > 1 || !(y1datasets.length)) {
                        return "#000000";
                    }
                    return y1datasets.length && y1datasets[0]['color'];
                })
                .text(y1label);

            if (scatter === 'bar') {
                var bar = svg.selectAll(".bar")
                    .data(bins)
                    .enter().append("g")
                    .attr("class", "bar")
                    .attr("fill", color)
                    .attr("transform", function(d) { return "translate(" + x_scale(d.x0) + "," + y1_scale(d.length) + ")"; });

                bar.append("rect")
                    .attr("x", 1)
                    .attr("title", function(d) { if (xscale === 'time' && timeformat) {
                        return d3.timeFormat(timeformat)(d.x0) + '-' + d3.timeFormat(timeformat)(d.x1) + ': ' + d.length + 'entries';
                    } else {
                        return d.x0 + '-' + d.x1 + ': ' + d.length + ' entries';
                    } })
                    .attr("width", x_scale(bins[0].x1) - (Math.max(0, x_scale(bins[0].x0) - 1)))
                    .attr("height", function(d) { return innerheight - y1_scale(d.length); });

            } else {

                var y1_draw_line = [], y2_draw_line = [];

                for (var p = 0; p < datasets.length; p++) {
                    if (datasets[p]['y1']) {
                        y1_draw_line.push(d3.line()
                            .curve(fit)
                            .x(function (d) {
                                return x_scale(d[0]);
                            })
                            .y(function (d) {
                                return y1_scale(d[1]);
                            }));
                    } else if (datasets[p]['y2']) {
                        y2_draw_line.push(d3.line()
                            .curve(fit)
                            .x(function (d) {
                                return x_scale(d[0]);
                            })
                            .y(function (d) {
                                return y2_scale(d[1]);
                            }));
                    }
                }

                if (y2data.length) {
                    svg.append("g")
                        .attr("class", "y axis")
                        .attr("transform", "translate(" + innerwidth + ", 0)")
                        .call(y2_axis)
                        .append("text")
                        .attr("transform", "translate(0," + innerheight / 2 + "), rotate(-90)")
                        .attr("y", 55)
                        .attr("dy", 0)
                        .style("text-anchor", "middle")
                        .attr("fill", function (_, i) {
                            if (y2datasets.length > 1) {
                                return "#000000";
                            }
                            return y2datasets[0]['color'];
                        })
                        .text(y2label);
                }

                var y1_data_lines = svg.selectAll(".d3_xy1_chart_line")
                    .data(y1datasets.map(function (d) {
                        return d3.zip(d.x, d.y1);
                    }))
                    .enter().append("g")
                    .attr("class", "d3_xy1_chart_line");
                var y2_data_lines = svg.selectAll(".d3_xy2_chart_line")
                    .data(y2datasets.map(function (d) {
                        return d3.zip(d.x, d.y2);
                    }))
                    .enter().append("g")
                    .attr("class", "d3_xy2_chart_line");

                for (var p = 0; p < y1_draw_line.length; p++) {
                    if (scatter === 'line') {
                        y1_data_lines.append("path")
                            .attr("class", "line")
                            .attr("d", function (d) {
                                return y1_draw_line[p](d);
                            })
                            .attr("data-legend", function (_, l) {
                                return y1datasets[l]['label'] || null;
                            })
                            .attr("stroke", function (_, l) {
                                return y1datasets[l]['color'];
                            })
                            .attr("fill", "none");
                    } else {
                        for (k = 0; k < y1datasets.length; k++) {
                            var newdata = y1datasets[k]['x'].map(function (e, j) {
                                return [e, y1datasets[k]['y1'][j]];
                            });
                            var data_points = svg.selectAll("dot")
                                .data(newdata)
                                .enter().append("circle")
                                .attr("r", 2)
                                .attr("cx", function (d) {
                                    return x_scale(d[0]);
                                })
                                .attr("cy", function (d) {
                                    return y1_scale(d[1]);
                                })
                                .attr("fill", function (_, l) {
                                    return y1datasets[k]['color'];
                                });
                        }
                    }
                }

                for (var p = 0; p < y2_draw_line.length; p++) {
                    if (scatter === 'line') {
                        y2_data_lines.append("path")
                            .attr("class", "line")
                            .attr("d", function (d) {
                                return y2_draw_line[p](d);
                            })
                            .attr("data-legend", function (_, l) {
                                return y2datasets[l]['label'] || null;
                            })
                            .attr("stroke", function (_, l) {
                                return y2datasets[l]['color'];
                            })
                            .attr("fill", "none");
                    } else {
                        for (k = 0; k < y2datasets.length; k++) {
                            var newdata = y2datasets[k]['x'].map(function (e, j) {
                                return [e, y2datasets[k]['y2'][j]];
                            });
                            var data_points = svg.selectAll("dot")
                                .data(newdata)
                                .enter().append("circle")
                                .attr("r", 2)
                                .attr("cx", function (d) {
                                    return x_scale(d[0]);
                                })
                                .attr("cy", function (d) {
                                    return y2_scale(d[1]);
                                })
                                .attr("fill", function (_, l) {
                                    return y2datasets[k]['color'];
                                });
                        }
                    }
                }



                legend = svg.append("g")
                    .attr("class", "legend")
                    .attr("transform", "translate(50,30)")
                    .call(d3.legend);


                /* Interactive stuff */
                var mouseG = svg.append("g")
                    .attr("class", "mouse-over-effects");

                mouseG.append("path") // this is the black vertical line to follow mouse
                    .attr("class", "mouse-line")
                    .style("stroke", "#333")
                    .style("stroke-width", "0.5px")
                    .style("opacity", "0");

                var lines = $(this).find('.line');

                if (y2datasets) {
                    var dualdatasets = [];
                    for (var p = 0; p < y1datasets.length; p++) {
                        dualdatasets.push({'x': y1datasets[p]['x'], 'y1': y1datasets[p]['y1']});
                    }
                    for (var p = 0; p < y2datasets.length; p++) {
                        dualdatasets.push({'x': y2datasets[p]['x'], 'y1': y2datasets[p]['y2'], 'scale': y2_scale});
                    }
                    var mousePerLine = mouseG.selectAll('.mouse-per-line')
                        .data(dualdatasets)
                        .enter()
                        .append("g")
                        .attr("class", "mouse-per-line");
                } else {
                    var mousePerLine = mouseG.selectAll('.mouse-per-line')
                        .data(datasets)
                        .enter()
                        .append("g")
                        .attr("class", "mouse-per-line");
                }

                mousePerLine.append("circle")
                    .attr("r", 2)
                    .style("fill", "none")
                    .style("stroke-width", "4px")
                    .style("opacity", "0");

                mousePerLine.append("text")
                    .attr("transform", "translate(10,3)");

                var mouseX = svg.append("text")
                    .attr("transform", "translate(" + (innerwidth - 3) + ", " + (innerheight - 3) + ")")
                    .style("text-anchor", "end")
                    .style("opacity", "0");

                mouseG.append('rect')
                    .attr('width', innerwidth)
                    .attr('height', innerheight)
                    .attr('fill', 'none')
                    .attr('pointer-events', 'all')
                    .on('mouseout', function () {
                        svg.select(".mouse-line").style("opacity", "0");
                        svg.selectAll(".mouse-per-line circle").style("opacity", "0");
                        svg.selectAll(".mouse-per-line text").style("opacity", "0");
                        mouseX.style("opacity", "1");
                    })
                    .on('mouseover', function (e) {
                        svg.select(".mouse-line").style("opacity", "1");
                        svg.selectAll(".mouse-per-line circle").style("opacity", "1");
                        svg.selectAll(".mouse-per-line text").style("opacity", "1");
                        mouseX.style("opacity", "1");

                    })
                    .on('mousemove', function () {
                        var mouse = d3.mouse(this);
                        svg.select(".mouse-line")
                            .attr("d", function () {
                                var d = "M" + mouse[0] + "," + innerheight;
                                d += " " + mouse[0] + "," + 0;
                                return d;
                            });
                        svg.selectAll(".mouse-per-line")
                            .style("stroke", function (d, n) {
                                return color_scale(n);
                            })
                            .attr("transform", function (d, n) {
                                var xPos = x_scale.invert(mouse[0]);
                                if (xscale === 'time') {
                                    mouseX.text("X = " + d3.timeFormat(timeformat)(xPos));
                                } else {
                                    mouseX.text("X = " + xPos.toFixed(2));
                                }
                                var closest = d['x'].reduce(function (prev, curr) {
                                    return (Math.abs(curr - xPos) < Math.abs(prev - xPos) ? curr : prev);
                                });
                                var i = d['x'].indexOf(closest);

                                var scale = d['scale'] || y1_scale;
                                var pos = scale(d['y1'][i]);
                                d3.select(this).select('text')
                                    .style("stroke", "none")
                                    .text(scale.invert(pos).toFixed(2));
                                return "translate(" + x_scale(closest) + "," + pos + ")";
                            });
                    });
                /* End of interactive stuff */
            }
            for (i = 0; i < notes.length; i++) {
                var xstart = notes[i]['xstart'] && x_scale(notes[i]['xstart']) || notes[i]['x'] && x_scale(notes[i]['x']) || 0,
                    xend = notes[i]['xend'] && x_scale(notes[i]['xend']) || notes[i]['x'] && x_scale(notes[i]['x']) || 0,
                    ystart = notes[i]['ystart'] && y1_scale(notes[i]['ystart']) || 0,
                    yend = notes[i]['yend'] && y1_scale(notes[i]['yend']) || innerheight - xoffset;
                svg.append("path")
                    .attr('class', notes[i]['label'] + ' ' + (notes[i]['class'] || '') + ' ' + (notes[i]['display'] !== null && (notes[i]['display'] === true && 'visible ' || 'hidden')) || 'visible')
                    .style("stroke", notes[i]['color'] || "#333")
                    .attr("d", function () {
                        var d = "M" + xstart + "," + yend;
                        d += " " + xend + "," + ystart;
                        return d;
                    });
                svg.append("text")
                    .attr('class', notes[i]['label'] + ' ' + (notes[i]['class'] || '') + ' ' + (notes[i]['display'] !== null && (notes[i]['display'] === true && 'visible ' || 'hidden')) || 'visible')
                    .text(notes[i]['label'])
                    .style("fill", notes[i]['color'] || "#333")
                    .attr("transform", "translate(" + (xstart + 3) + "," + (y1_scale(0) + xoffset / 2) + "), rotate(-90)")
                    .style("text-anchor", "middle");
            }

        });

    }

    chart.width = function (value) {
        if (!arguments.length) return width;
        width = value;
        return chart;
    };

    chart.height = function (value) {
        if (!arguments.length) return height;
        height = value;
        return chart;
    };

    chart.xlabel = function (value) {
        if (!arguments.length) return xlabel || '';
        xlabel = value;
        return chart;
    };

    chart.y1label = function (value) {
        if (!arguments.length) return y1label;
        y1label = value;
        return chart;
    };

    chart.y2label = function (value) {
        if (!arguments.length) return y2label;
        y2label = value;
        return chart;
    };

    chart.xscale = function (value) {
        if (!arguments.length) return xscale;
        xscale = value;
        return chart;
    };
    chart.scatter = function (value) {
        if (!arguments.length) return scatter;
        scatter = value;
        return chart;
    };
    chart.notes = function (value) {
        if (!arguments.length) return notes || [];
        notes = value;
        return chart;
    };
    chart.interpolation = function (value) {
        if (!arguments.length) return interpolation;
        interpolation = value;
        return chart;
    };
    chart.xlimits = function (value) {
        if (!arguments.length) return xlimits || [null, null];
        xlimits = value;
        return chart;
    };
        chart.y1limits = function (value) {
        if (!arguments.length) return y1limits || [null, null];
        y1limits = value;
        return chart;
    };
    chart.y2limits = function (value) {
        if (!arguments.length) return y2limits || [null, null];
        y2limits = value;
        return chart;
    };
    chart.binning = function (value) {
        if (!arguments.length) return binning;
        binning = value;
        return chart;
    };
    chart.timeformat = function (value) {
        if (!arguments.length) return timeformat;
        timeformat = value;
        return chart;
    };

    return chart;
}


function build_report(selector, report) {
    $(selector).addClass('report-viewer');
    var converter = new showdown.Converter();
    var color_scheme = d3.schemeSet2.concat(d3.schemeDark2);

    $.each(report['details'], function (i, section) {
        var section_box = $(selector).append('<section id="section-' + i + '"></section>').children(":last-child");
        if (section['title']) {
            section_box.append("<h3 class='col-12 section-title' >" + section['title'] + "</h3>");
        }
        section_box.addClass(section['style'] || 'col-12');
        if (section['description']) {
            section_box.append("<div class='col-12'>" + converter.makeHtml(section['description']) + "</div>");
        }
        $.each(section['content'], function (j, entry) {
            var entry_row = section_box.append("<div id='entry-" + i + "-" + j + "'></div>").children(":last-child");
            entry_row.addClass(entry['style'] || '');
            if (entry['title']) {
                if (!entry['kind']) {
                    entry_row.append("<h4>" + entry['title'] + "</h4>")
                }
            }
            if (entry['description']) {
                entry_row.append("<div class='description'>" + converter.makeHtml(entry['description']) + "</div>")
            }
            if (entry['kind'] === 'table') {
                if (entry['data']) {
                    var table = $("<table id='table-" + i + "-" + j + "' class='table table-hover table-sm'></table>");
                    var thead = $('<thead></thead>');
                    var tbody = $('<tbody></tbody>');

                    $.each(entry['data'], function (l, line) {
                        if (line) {
                            var tr = $('<tr></tr>');
                            for (k = 0; k < line.length; k++) {
                                if ((k === 0 && entry['header'].includes('column')) || (l === 0 && entry['header'].includes('row'))) {
                                    var td = $('<th></th>').text(line[k]);
                                } else {
                                    var td = $('<td></td>').text(line[k]);
                                }
                                tr.append(td);
                            }
                            if (entry['header'].includes('row') && l === 0) {
                                thead.append(tr);
                            } else {
                                tbody.append(tr);
                            }
                        }
                    });
                    if (entry['title']) {
                        table.append("<caption class='text-center'>" + entry['title'] + "</caption>");
                    }
                    table.append(thead);
                    table.append(tbody);
                    entry_row.append(table);
                }
            } else if (entry['kind'] === 'barchart') {
                $("#entry-" + i + "-" + j).append("<figure id='figure-" + i + "-" + j + "'></figure>");
                var data = entry['data']['data'];
                //Draw Stack Chart
                var margin = { top: 20, right: 20, bottom: 50, left: 40 },
                    width = $('#figure-' + i + "-" + j).width() - margin.left - margin.right,
                    height = width*9/16;

                var x = d3.scaleBand().range([0, width]).padding(0.1);
                var y = d3.scaleLinear().range([height, 0]);
                var colors = d3.scaleOrdinal(entry['data']['colors'] || color_scheme);

                var canvas = d3.select('#figure-' + i + '-' + j).append("svg").attr('id', 'plot-' + i + "-" + j)
                    .attr("viewBox", "0 0 "+ (width + margin.left + margin.right) + " " + (height + margin.top + margin.bottom))
                    .append("g")
                    .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

                drawStackChart(data, entry['data']['x-label'], canvas, colors, x, y, height);

                if (entry['title']) {
                    $('#figure-' + i + '-' + j).append("<figcaption class='text-center'>Figure " + ($('figure').length + 1) + '. ' + entry['title'] + "</figcaption>")
                }
            } else if (entry['kind'] === 'lineplot' || entry['kind'] === 'scatterplot' || entry['kind'] === 'histogram') {
                $("#entry-" + i + "-" + j).append("<figure id='figure-" + i + "-" + j + "'></figure>");
                var data = [];
                var xlabel = entry['data']['x-label'] || (entry['data']['x'] && entry['data']['x'].shift()) || null;
                var xscale = entry['data']['x-scale'] || 'linear';
                var xlimits = entry['data']['x-limits'] || [null, null];
                var y1limits = entry['data']['y1-limits'] || [null, null];
                var y2limits = entry['data']['y2-limits'] || [null, null];
                var interpolation = entry['data']['interpolation'] || 'linear';
                var annotations = entry['data']['annotations'] || [];
                var binning = entry['data']['bins'] || 50;
                var timeformat = entry['data']['time-format'] || null;
                var y1label = '', y2label = '';
                if (entry['kind'] === 'histogram') {
                    data = {'data': entry['data']['data'], 'color': entry['data']['color'] || choose(color_scheme)};
                    if (xscale == 'time') {
                        $.each(data['data'], function(i, d) {
                            data['data'][i] = new Date(d)
                        });
                    }
                } else {
                    if (xscale == 'time') {
                        $.each(entry['data']['x'], function(l, line) {
                           entry['data']['x'][l] = new Date(line);
                        });
                    }
                    $.each(entry['data']['y1'], function (l, line) {
                        y1label = line.shift();
                        data.push({'label': y1label, 'x': entry['data']['x'], 'y1': line});
                    });

                    $.each(entry['data']['y2'], function (l, line) {
                        y2label = line.shift();
                        data.push({'label': y2label, 'x': entry['data']['x'], 'y2': line});
                    });
                }
                var width = $('#figure-' + i + "-" + j).width();
                y1label = entry['data']['y1-label'] || y1label;
                y2label = entry['data']['y2-label'] || y2label;
                var xy_chart = draw_xy_chart()
                    .width(width)
                    .height(width*9/16)
                    .xlabel(xlabel)
                    .y1label(y1label)
                    .y2label(y2label)
                    .xlimits(xlimits)
                    .y1limits(y1limits)
                    .y2limits(y2limits)
                    .xscale(xscale)
                    .notes(annotations)
                    .binning(binning)
                    .timeformat(timeformat)
                    .interpolation(interpolation)
                    .scatter(entry['kind'] === 'scatterplot' && 'scatter' || entry['kind'] === 'lineplot' && 'line' || entry['kind'] === 'histogram' && 'bar');
                var svg = d3.select('#figure-' + i + '-' + j).append("svg")
                    .attr("viewBox", "0 0 "+ width + " " + (width*9/16))
                    .attr('id', 'plot-' + i + "-" + j)
                    .datum(data)
                    .call(xy_chart);
                if (entry['title']) {
                    $('#figure-' + i + '-' + j).append("<figcaption class='text-center'>" + entry['title'] + "</figcaption>")
                }
            } else if (entry['kind'] === 'pie' || entry['kind'] === 'gauge') {
                $("#entry-" + i + "-" + j).append("<figure id='figure-" + i + "-" + j + "'></figure>");
                var data = [];
                var width = entry_row.width();
                var totalAngle = 0;

                $.each(entry['data'], function (l, wedge) {
                    if ((entry['data'][l]['start'] || totalAngle) != totalAngle) {
                        data.push({'start': totalAngle, 'value': entry['data'][l]['start'] - totalAngle, 'color': '#ffffff'});
                        totalAngle += entry['data'][l]['start'] - totalAngle;
                    }
                    wedge['start'] = wedge['start'] || totalAngle;
                    data.push(wedge);
                    totalAngle += entry['data'][l]['value'];
                });

                var pie_chart = draw_pie_chart()
                    .width(width)
                    .height(width*9/16)
                    .innerRadius(entry['kind'] === 'gauge' && 0.5 || 0);
                var svg = d3.select('#figure-' + i + '-' + j).append("svg")
                    .attr("viewBox", "0 0 "+ width + " " + (width*9/16))
                    .attr('id', 'plot-' + i + "-" + j)
                    .attr('class', 'gauge')
                    .datum(data)
                    .call(pie_chart);
                if (entry['title']) {
                    $('#figure-' + i + '-' + j).append("<figcaption class='text-center'>" + entry['title'] + "</figcaption>")
                }
            }
            if (entry['notes']) {
                entry_row.append("<div class='notes'>" + converter.makeHtml(entry['notes']) + "</div>");
            }
        });
    });

}

(function ($) {
    $.fn.liveReport = function (options) {
        let target = $(this);
        let defaults = {
            data: {},
            scheme: d3.schemeSet2
        };
        let settings = $.extend(defaults, options);

        target.addClass('report-viewer');
        build_report(this, settings.data)

    };
}(jQuery));