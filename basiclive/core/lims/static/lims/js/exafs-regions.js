Array.prototype.insert = function ( index, item ) {
    this.splice( index, 0, item );
};
String.prototype.strip = function()
{
    return String(this).replace(/^\s+|\s+$/g, '');
};

function uuid4() {
  return ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
    (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16)
  );
}

function expand_data(regions) {
    let lpad =  {...regions[0]};
    let rpad =  {...regions[regions.length-1]};

    lpad.end = lpad.start
    lpad.start = -400;

    rpad.start = rpad.end
    rpad.end = -850;

    regions.insert(0, lpad);
    regions.insert(regions.length, rpad)
    //regions.sort(function(a,b){ return d3.ascending(a.start, b.start)});
    return regions;
}

(function ( $ ) {
    $.fn.selectRegions = function (selector) {
        let container = d3.select($(this)[0]);
        let target = d3.select(selector);
        let extent = {start: -400, end: 850};

        let count = 1;
        let regions = [
            {start: extent.start, end: -200 , step: 1, time: 1.0, kspace: false, id: count++, index: 0},
            {start: -200, end: 700 , step: 1, time: 1.0, kspace: false, id: count++, index: 1},
            {start: 700, end: extent.end , step: 1, time: 1.0, kspace: false, id: count++, index: 2}
        ];

        try {
            regions = expand_data(JSON.parse(target.text()));
        } catch(err) {
        }

        function ev2k(energy) {
            const H = (4.135667516e-15)/(2 * Math.PI);  // eV.s
            const M = 5.685629904369271e-32;  // eV.A^-2
            return Math.sign(energy) * Math.sqrt(2 * M * Math.abs(energy)) / H;
        }

        const font = "10px Fira Code";
        const margin = { top: 10, right: 15, bottom: 50, left: 15};
        const width = 500;
        const height = width * 0.33;
        const spectrum = make_spectrum();
        const escale = d3.scaleLinear().range([0, width]).domain([extent.start, extent.end]);
        const kscale = d3.scalePow().exponent(2).range([0, width]).domain([ev2k(extent.start), ev2k(extent.end)]);
        const eaxis = d3.axisBottom().scale(escale).ticks(15);
        const kaxis = d3.axisBottom().scale(kscale).ticks(8).tickFormat(x => x < 0 ? "" : x);

        const svg = container.append("svg")
            .attr('viewBox', `-${margin.left} -${margin.top} ${width+margin.left + margin.right} ${height + margin.top + margin.bottom}`)
            .attr('id', 'sel-canvas');

        // eV-axis
        svg.append("g")
            .attr('transform', `translate(0, ${height+1})`)
            .style("font", font)
            .call(eaxis);
        svg.append("text")
            .attr('transform', `translate(${width+2}, ${height+1})`)
            .style("font", font)
            .text("eV");

        // K-axis
        svg.append("g")
            .attr('transform', `translate(0, ${height+margin.bottom/2})`)
            .style("font", font)
            .call(kaxis);
        svg.append("text")
            .attr('transform', `translate(${width+2}, ${height+margin.bottom/2})`)
            .style("font", font)
            .text("k");

        const tooltip = svg.append("g");

        svg.on('mouseleave', function(){
            tooltip.call(callout, null);
        });

        // Add the line
        svg.append("path")
            .datum(spectrum)
            .attr("fill", "none")
            .attr("stroke", "black")
            .attr("stroke-width", 1)
            .attr("d", d3.line()
                .x(d => escale(d.x))
                .y(d => height - d.y)
            );

        draw(regions);

        function make_spectrum() {
            let data = [];
            let decay = 0.99999;
            let value = 0;
            let ripple = 0;
            for (let x = extent.start, i = 0; x < extent.end; x++, i++) {
                ripple = x < 0 ? 0 : Math.exp(-i*0.005)*height*Math.sin(0.1*x);
                value = (height/5 + 0.5*height/(1 + Math.exp(-0.25*x)) + ripple);
                data.push({"x": x, "y": parseFloat(value.toFixed(2))});
            }
            return data;
        }

        function callout(g, value) {
            if (!value) return g.style("display", "none");

            value = `${value.toFixed(1)} eV`;

            g.style("display", null)
                .style("font", font)
                .style("opacity", 0.75)
                .style("pointer-events", "none");

            const path = g.selectAll("path")
                .data([null])
                .join("path")
                .attr("fill", "yellow")
                .attr("stroke", "black");

            const text = g.selectAll("text")
                .data([null])
                .join("text")
                .call(text => text
                    .selectAll("tspan")
                    .data((value + "").split(/\n/))
                    .join("tspan")
                    .attr("x", 0)
                    .attr("y", (d, i) => `${i * 1.1}rem`)
                    .text(d => d));

            const {x, y, width: w, height: h} = text.node().getBBox();

            text.attr("transform", `translate(${-w / 2},${10 - y})`);
            path.attr("d", `M${-w / 2 - 5},5H-5l5,-5l5,5H${w / 2 + 5}v${h + 10}h-${w + 10}z`);
        }

        function draw(regions) {
            // re-index data
            regions.forEach(function(d, i) {d.index = i;});
            var bars =svg.selectAll('rect')
                .data(regions, function(d){return d.start;});

            bars.exit()
                .transition()
                .duration(100)
                .attr('width', 0)
                .remove();

            bars.enter()
                .append("rect")
                .attr('x', function(d) { return escale(d.end);})
                .attr('width', 0)
                .attr('height', height)
                .attr('y', 0)
                .on('mouseover', function(d){
                    d3.select(`#region-${d.id}`).selectAll('td').style('background', 'rgb(255, 255, 0, 0.25)');
                })
                .on('mouseout', function(d){
                    d3.select(`#region-${d.id}`).selectAll('td').style('background', null);
                })
                .on('mousemove', function(){
                    let mouse = d3.mouse(this);
                    tooltip
                        .attr("transform", `translate(${mouse[0]}, ${height+3})`)
                        .call(callout, escale.invert(mouse[0]));
                })
                .on('contextmenu', function(d){
                    d3.event.preventDefault();
                    //remove this region
                    if (regions.length > 3) {
                        if (d.index <  regions.length - 1) {
                            regions[d.index + 1].start = d.start;
                        } else {
                            regions[d.index - 1].end = d.end;
                        }
                        regions.splice(d.index, 1);
                    }
                    draw(regions);
                })
                .on('click',  function(d){
                    //add new region
                    let pt = d3.mouse(this);
                    let reg =  {...d};
                    reg.id = count++;
                    reg.start = parseFloat(escale.invert(pt[0]).toFixed(1));
                    d.end = reg.start;
                    regions.push(reg);
                    regions.sort(function(a,b){ return d3.ascending(a.start, b.start)});
                    draw(regions);
                })
                .attr('stroke', "white")
                .attr('height', height)
                .attr('y', 0)
                .merge(bars).transition()
                .duration(100)
                .attr('fill', function(d) { return ((d.index > 0) && (d.index < regions.length - 1)) ? 'rgba(195, 20, 165, 0.45)' : 'rgba(0, 0, 0, 0.45)'; })
                .attr('x', function(d) { return escale(d.start);})
                .attr('width', function(d) {return escale(d.end) - escale(d.start); });
                tabulate(regions.slice(1, regions.length -1));
        }

        function edit_data(index, field, value) {
            if (field === 'start') {
                if (regions[index].end > value ) {
                    regions[index - 1].end = value;
                    regions[index].start = value;
                }
            } else if (field === 'end'){
                if (value > regions[index].start ) {
                    regions[index].end = value;
                    regions[index + 1].start = value;
                }
            } else {
                regions[index][field] = value;
            }
            draw(regions);
        }

        function tabulate(data) {
            // create a row for each object in the data
            var columns = ['index', 'start', 'end', 'step', 'time', 'kspace']
            var rows = d3.select('#table').selectAll('tr').data(data, d => d.id);
            rows.exit().remove();
            var tr = rows.enter().append('tr').attr('id', d => `region-${d.id}`).merge(rows);

            // create new cell for each cell in row
            var cells = tr.selectAll('td')
                .data(function (row) {
                    return columns.map(function (column) {
                      return {key: column, value: row[column], index: row.index};
                    });
                });
            cells.exit().remove();
            cells.enter().append('td')
                .attr('contenteditable', d => ['index', 'kspace'].includes(d.key) ? false : true)
                .on("focusout", function(d, i){
                    let cell = d3.select(this);
                    let value = d.key == 'kspace' ? cell.text().strip() === 'true' : parseFloat(cell.text());
                    if ([NaN, undefined].includes(value)) {
                        value = d.value;
                        console.log(value, d.value);
                        cell.text(value);
                    }
                    edit_data(d.index, d.key, value);
                })
                .on("click",function(d, i){
                    if (d.key === 'kspace') {
                        edit_data(d.index, d.key, !d.value);
                    }
                })
                .on("keydown", function(d, i){
                    // prevent Enter or Space
                    if ([13, 32].includes(d3.event.keyCode)) {
                        d3.event.preventDefault();
                    }
                })
                .merge(cells).text(d => d.value);
            target.text(JSON.stringify(data));

        }

    };
}(jQuery));


(function ( $ ) {
    $.fn.showRegions = function (data) {
        let target = d3.select($(this)[0]);

        console.log(target, data, $(this));

        // create a row for each object in the data
        let table = target.append('table').attr('class', 'table table-sm regions');
        let thead = table.append('thead');
        let tbody = table.append('tbody');
        let columns = ['index', 'start', 'end', 'step', 'time', 'kspace'];
        let headers = ['#', 'Start', 'End', 'Step', 'Time', 'k-space'];

        thead.append('tr').selectAll('th')
            .data(headers).enter()
            .append('th')
            .text(d => d);

        let rows = tbody.selectAll('tr')
            .data(data, d => d.id)
            .enter()
            .append('tr')
            .attr('id', d => `region-${d.id}`);

        // create new cell for each cell in row
        rows.selectAll('td')
            .data(function (row) {
                return columns.map(function (column) {
                  return {key: column, value: row[column], index: row.index};
                });
            })
            .enter().append('td')
            .text(d => d.value);
    };
}(jQuery));