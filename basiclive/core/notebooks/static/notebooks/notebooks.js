// initialize name space for application global variables
const MyelnNotebooks = window.MyelnNotebooks || {};
window.MyelnNotebooks = MyelnNotebooks;

function getCsrfToken() {
    if (window.jQuery && typeof jQuery.cookie === 'function') {
        const token = jQuery.cookie('csrftoken');
        if (token) return token;
    }
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
}

function get_entry_data_url(pk) {
    const btn = $(`#entry-${pk} .edit-button`);
    return btn.data('url') || `/notebooks/entry/${pk}/`;
}

function getDomElement(element) {
    if (!element) return null;
    if (element instanceof jQuery || (element && element.jquery && element.length)) {
        return element[0];
    }
    if (typeof element === 'string') {
        return document.querySelector(element);
    }
    return element;
}

function showPopover(element, options) {
    const el = getDomElement(element);
    if (!el) return;
    if (window.bootstrap && bootstrap.Popover) {
        const instance = bootstrap.Popover.getOrCreateInstance(el, options);
        instance.show();
        return instance;
    } else if ($.fn.popover) {
        $(el).popover(options);
        $(el).popover('show');
    }
}

function hidePopover(element) {
    const el = getDomElement(element);
    if (!el) return;
    if (window.bootstrap && bootstrap.Popover) {
        const instance = bootstrap.Popover.getInstance(el);
        if (instance) instance.hide();
    } else if ($.fn.popover) {
        $(el).popover('hide');
    }
}

function disposePopover(element) {
    const el = getDomElement(element);
    if (!el) return;
    if (window.bootstrap && bootstrap.Popover) {
        const instance = bootstrap.Popover.getInstance(el);
        if (instance) instance.dispose();
    } else if ($.fn.popover) {
        $(el).popover('dispose');
    }
}

function disposeTooltips(container) {
    const $c = $(container);
    const elements = $c.find('[data-bs-original-title], [data-original-title], [title]').add($c.filter('[data-bs-original-title], [data-original-title], [title]')).get();
    elements.forEach(function(el) {
        if (window.bootstrap && bootstrap.Tooltip) {
            const inst = bootstrap.Tooltip.getInstance(el);
            if (inst) inst.dispose();
        } else if ($.fn.tooltip) {
            $(el).tooltip('dispose');
        }
    });
}

// Helper functions to implement sketcher toolbar
function set_sketch_mode(kind) {
    if (MyelnNotebooks.sketcher) {
        MyelnNotebooks.sketcher.mode = kind;
    }
    $("[class*='btn-mode-']").removeClass("active");
    $(".btn-mode-" + kind).addClass("active");
}

// SimpleMDE custom button functions
function togglePreview(editor) {
    SimpleMDE.togglePreview(editor);
    $(".editor-preview").each(function() {
        if (typeof renderMathInElement === "function") {
            renderMathInElement(this);
        }
    });
}

function wrapSelection(editor, delimeter) {
    const cm = editor.codemirror;
    const output = "";
    const selectedText = cm.getSelection();
    const text = selectedText || output;

    const startPoint = cm.getCursor("start");
    const newOutput = delimeter + text;
    cm.replaceSelection(newOutput);

    const endPoint = cm.getCursor("end");
    cm.setSelection(startPoint, endPoint);
    cm.replaceSelection(newOutput + delimeter);

    cm.setSelection(endPoint, endPoint);
    cm.focus();
}

function wrapEquation(editor) {
    return wrapSelection(editor, "$$");
}

// Modal Lifecycle & Rich Editor Initializations for Entry Forms

function initTextModal($modal) {
    const $textarea = $modal.find("#entry-text-editor");
    if (!$textarea.length || $textarea.data("simplemde-initialized")) return;
    $textarea.data("simplemde-initialized", true);

    const textareaEl = $textarea[0];
    const simplemde = new SimpleMDE({
        autoDownloadFontAwesome: false,
        renderingConfig: {
            codeSyntaxHighlighting: true,
        },
        element: textareaEl,
        spellChecker: false,
        status: false,
        toolbar: [{
            name: "heading",
            action: SimpleMDE.toggleHeadingSmaller,
            className: "mi mi-type mi-md",
            title: "Heading"
        }, "|", {
            name: "bold",
            action: SimpleMDE.toggleBold,
            className: "mi mi-bold mi-md",
            title: "Bold"
        }, {
            name: "italic",
            action: SimpleMDE.toggleItalic,
            className: "mi mi-italic mi-md",
            title: "Italics"
        }, "|", {
            name: "quote",
            action: SimpleMDE.toggleBlockquote,
            className: "mi mi-quote mi-md",
            title: "Quote"
        }, "|", {
            name: "unordered-list",
            action: SimpleMDE.toggleUnorderedList,
            className: "mi mi-list-ul mi-md",
            title: "Bullet List"
        }, {
            name: "ordered-list",
            action: SimpleMDE.toggleOrderedList,
            className: "mi mi-list-ol mi-md",
            title: "Numbered List"
        }, "|", {
            name: "link",
            action: SimpleMDE.drawLink,
            className: "mi mi-link mi-md",
            title: "Link"
        }, "|", {
            name: "Equation (Latex Syntax)",
            action: wrapEquation,
            className: "mi mi-math mi-md",
            title: "Equation (latex syntax)",
        }, "|", {
            name: "undo",
            action: SimpleMDE.undo,
            className: "mi mi-undo mi-md",
            title: "Undo"
        }, {
            name: "redo",
            action: SimpleMDE.redo,
            className: "mi mi-redo mi-md",
            title: "Redo"
        }, "|", {
            name: "preview",
            action: togglePreview,
            className: "mi mi-eye mi-md no-disable",
            title: "Preview"
        }]
    });
    MyelnNotebooks.simplemde = simplemde;

    setTimeout(function() {
        simplemde.codemirror.refresh();
    }, 100);

    simplemde.codemirror.on("change", function() {
        textareaEl.value = simplemde.value();
    });

    const $form = $textarea.closest("form");
    function syncMarkdown() {
        if (MyelnNotebooks.simplemde) {
            textareaEl.value = MyelnNotebooks.simplemde.value();
        }
    }
    $form.on("submit", syncMarkdown);
    $form.find(":submit").on("click", syncMarkdown);
}

function initSketchModal($modal) {
    const $sketchInput = $modal.find("#sketch-data-input, input[name='sketch_data']");
    if (!$sketchInput.length || $sketchInput.data("atrament-initialized")) return;
    $sketchInput.data("atrament-initialized", true);

    const $container = $('<div id="modal-sketch-container" class="mb-3"></div>');
    const $fileDiv = $modal.find("#div_id_file").length ? $modal.find("#div_id_file") : $sketchInput.parent();
    $fileDiv.before($container);

    const width = Math.min($container.width() || $modal.find(".modal-body").width() || 480, 560);
    const height = Math.round(width * 4.5 / 9);

    $container.append('<div class="editor-toolbar sketcher-toolbar"></div>');
    $container.append('<div class="sketch-canvas-wrapper border rounded-bottom"><canvas id="sketcher"></canvas></div>');

    if (typeof atrament === "function") {
        const sketcher = atrament("#sketcher", width, height);
        MyelnNotebooks.sketcher = sketcher;
        sketcher.adaptiveStroke = false;

        const tb = $container.find(".sketcher-toolbar");
        const tbbtn = [
            ["a", "", "MyelnNotebooks.sketcher.clear();", "Clear canvas", "mi-trash"],
            ["|"],
            ["a", "btn-mode-draw active", "set_sketch_mode(`draw`);", "Draw", "mi-pencil"],
            ["a", "btn-mode-fill", "set_sketch_mode(`fill`);", "Fill", "mi-fill"],
            ["a", "btn-mode-erase", "set_sketch_mode(`erase`);", "Erase", "mi-erase"],
            ["|"],
            ["a", "active", "MyelnNotebooks.sketcher.smoothing=!MyelnNotebooks.sketcher.smoothing; $(this).toggleClass(`active`);", "Auto-smoothing", "mi-activity"],
            ["a", "", "MyelnNotebooks.sketcher.adaptiveStroke=!MyelnNotebooks.sketcher.adaptiveStroke; $(this).toggleClass(`active`);", "Adaptive Stroke", "mi-stroke"],
            ["|"],
            ["color", "btn btn-link", "MyelnNotebooks.sketcher.color=event.target.value;", "Color", ""],
            ["|"],
            ["span", "active", "MyelnNotebooks.sketcher.weight=parseFloat(event.target.value);", "Line width", "mi-edit-line", "0.5", "40", "0.5", "0.5"],
            ["|"],
            ["span", "", "MyelnNotebooks.sketcher.opacity=parseFloat(event.target.value);", "Opacity", "mi-star-half", "0", "1", "0.05", "1"]
        ];

        $.each(tbbtn, function (i, data) {
            let html = "";
            if (data[0] === "|") {
                html = "<i class='separator'></i>";
            } else {
                if (data[0] === "a") {
                    html = "<a title='{3}' onclick='{2}' tabindex='" + i + "' class='mi {1} mi-md {4}'></a>";
                } else if (data[0] === "color") {
                    html = "<div id='colorPicker'><a class='color' title='{3}'><div class='colorInner'></div></a><div class='track'></div><input type='hidden' class='colorInput' value='#000000'/></div>";
                } else {
                    html = "<span class='mi {1} mi-md {4}' title='{3}'><input type='range' min='{5}' max='{6}' oninput='{2}' value='{8}' step='{7}'></span>";
                }
                $.each(data, function (k, v) {
                    html = html.replace("{" + k + "}", v);
                });
            }
            tb.append(html);
        });

        const picker = document.querySelector("#colorPicker");
        if (picker && typeof Picker !== "undefined") {
            const colorButton = $("#colorPicker .color");
            const cp = new Picker(picker);
            cp.onChange = function(color) {
                colorButton.css("background-color", color.rgbaString);
                sketcher.color = color.rgbaString;
            };
        }

        const existingFileUrl = $modal.find("#div_id_file a[href]").attr("href");
        if (existingFileUrl) {
            const canvas = document.getElementById("sketcher");
            if (canvas) {
                const ctx = canvas.getContext("2d");
                const img = new Image();
                img.onload = function() {
                    let sx = img.width;
                    let sy = img.height;
                    let scale = Math.min(width / sx, height / sy);
                    let x = (width - sx * scale) / 2;
                    let y = (height - sy * scale) / 2;
                    ctx.drawImage(img, x, y, sx * scale, sy * scale);
                };
                img.src = existingFileUrl;
            }
        }
    }

    const $form = $sketchInput.closest("form");
    function syncSketch() {
        if (MyelnNotebooks.sketcher) {
            const b64 = MyelnNotebooks.sketcher.toImage();
            $sketchInput.val(b64);
        }
    }
    $form.on("submit", syncSketch);
    $form.find(":submit").on("click", syncSketch);
}

function initDataModal($modal) {
    const $dataEditor = $modal.find("#entry-data-editor");
    if (!$dataEditor.length || $dataEditor.data("table-initialized")) return;
    $dataEditor.data("table-initialized", true);

    const itext = $dataEditor.val();
    $dataEditor.hide();

    const table_toolbar = (
        '<div class="editor-toolbar" id="table-toolbar">' +
        '<a title="Add Column" tabindex="-1" class="mi mi-add-col mi-md text-primary" id="table-add-col"></a>' +
        '<i class="separator">|</i>' +
        '<a title="Remove Column" tabindex="-1" class="mi mi-del-col mi-md text-danger" id="table-del-col"></a>' +
        '<i class="separator">|</i>' +
        '<a title="Add Row" tabindex="-1" class="mi mi-add-row mi-md text-primary" id="table-add-row"></a>' +
        '<i class="separator">|</i>' +
        '<a title="Remove Row" tabindex="-1" class="mi mi-del-row mi-md text-danger" id="table-del-row"></a>' +
        '</div>'
    );

    const $container = $('<div id="modal-table-container" class="mb-3"></div>');
    $container.html(table_toolbar + '<div class="table-editable table-responsive border rounded-bottom" style="max-height: 400px; overflow: auto;"></div><div class="drop-csv text-muted small mt-1">Drag and drop a .csv or .xdi file onto the table to import data.</div>');
    $dataEditor.before($container);

    if ($.fn.myelnTable) {
        MyelnNotebooks.table = $container.find(".table-editable").myelnTable({
            "initial": itext
        });
    }

    $container.find(".table-editable").on("dragover", function(e) {
        e.preventDefault();
    }).on("drop", function(e) {
        e.preventDefault();
        const dt = e.originalEvent.dataTransfer;
        if (dt && dt.files && dt.files.length && MyelnNotebooks.table) {
            const file = dt.files[0];
            const reader = new FileReader();
            reader.readAsText(file);
            reader.onloadend = function() {
                if (file.type === "text/csv" || file.name.endsWith(".csv")) {
                    MyelnNotebooks.table.csv2JSON(reader.result);
                } else if (file.name.split(".").pop() === "xdi") {
                    MyelnNotebooks.table.xdi2JSON(reader.result);
                }
            };
        }
    });

    const $form = $dataEditor.closest("form");
    function syncTable() {
        if (MyelnNotebooks.table) {
            const table_json = MyelnNotebooks.table.exportJSON();
            $dataEditor.val(table_json);
        }
    }
    $form.on("submit", syncTable);
    $form.find(":submit").on("click", syncTable);
}

function initFileDropzoneModal($modal) {
    const $fileInput = $modal.find("input[type='file'][name='file'].dropzone-target");
    if (!$fileInput.length || $modal.find("#sketch-data-input").length || $fileInput.data("dropzone-initialized")) return;
    $fileInput.data("dropzone-initialized", true);

    if (typeof Dropzone === "undefined") return;

    Dropzone.autoDiscover = false;
    const acceptedFiles = $fileInput.attr("accept") || null;
    const dropzoneHtml = (
        `<div id="modal-file-dropzone" 
            class="dropzone mb-2 rounded border p-3 text-center" 
            style="cursor: pointer; min-height: 110px;"
        >  
            <div class="dz-message needsclick my-2">
                <span class="small">Drop file here or click to browse</span>  
            </div>
        </div>`
    );
    $fileInput.before(dropzoneHtml);

    try {
        const myDropzone = new Dropzone("#modal-file-dropzone", {
            url: "#",
            autoProcessQueue: false,
            uploadMultiple: false,
            acceptedFiles: acceptedFiles,
            maxFiles: 1,
            init: function() {
                MyelnNotebooks.myDropzone = this;
            },
            accept: function(file, done) {
                if (this.files.length > 1) {
                    this.removeFile(this.files[0]);
                }
                try {
                    const dataTransfer = new DataTransfer();
                    dataTransfer.items.add(file);
                    $fileInput[0].files = dataTransfer.files;
                    $fileInput.trigger("change");
                } catch (err) {
                    console.warn("DataTransfer file sync not supported:", err);
                }
                done();
            }
        });
    } catch (err) {
        console.warn("Dropzone initialization failed:", err);
    }
}

function initModalEntryEditors(modalElement) {
    const $modal = $(modalElement || "#modal-target");
    initTextModal($modal);
    initSketchModal($modal);
    initDataModal($modal);
    initFileDropzoneModal($modal);
}

// Modal lifecycle bindings for Entry forms
$(document).on("shown.bs.modal", function(e) {
    const modalEl = e.target;
    if ($(modalEl).closest("#modal-target").length || modalEl.id === "modal") {
        initModalEntryEditors(modalEl);
    }
});

$(document).on("hidden.bs.modal", function(e) {
    const modalEl = e.target;
    if ($(modalEl).closest("#modal-target").length || modalEl.id === "modal") {
        if (MyelnNotebooks.simplemde) {
            try { MyelnNotebooks.simplemde.toTextArea(); } catch(_) {}
            MyelnNotebooks.simplemde = null;
        }
        if (MyelnNotebooks.sketcher) {
            MyelnNotebooks.sketcher = null;
        }
        if (MyelnNotebooks.table) {
            MyelnNotebooks.table = null;
        }
        if (MyelnNotebooks.myDropzone) {
            try { MyelnNotebooks.myDropzone.destroy(); } catch(_) {}
            MyelnNotebooks.myDropzone = null;
        }
    }
});

// Observe dynamic DOM updates inside #modal-target (e.g. form re-render after validation errors)
if (typeof MutationObserver !== "undefined") {
    const modalTargetObserver = new MutationObserver(function() {
        const $modalTarget = $("#modal-target");
        if ($modalTarget.find(".modal.show, #modal.show").length) {
            initModalEntryEditors($modalTarget);
        }
    });
    $(document).ready(function() {
        const targetNode = document.getElementById("modal-target");
        if (targetNode) {
            modalTargetObserver.observe(targetNode, { childList: true, subtree: true });
        }
    });
}

//tables
(function ( $ ) {
    $.fn.myelnTable = function (options) {

        const table = $(this);
        let selectedRow = null;
        let selectedCol = null;
        const toolbar = $('#table-toolbar');

        buildTable(options ? options['initial'] : null);

        function colName(num) {
            let ret = '';
            for (let a = 1, b = 26; (num -= a) >= 0; a = b, b *= 26) {
                ret = String.fromCharCode(parseInt((num % b) / a, 10) + 65) + ret;
            }
            return ret;
        }

        function renumberRows() {
            table.find('tbody tr').each(function(){
                $(this).find('th.row-index').html($(this).index() + 1);
            });
        }

        function renameHeaders() {
            table.find('thead th.header').each(function(){

            });
        }

        function caret(event) {
            const sel = document.getSelection();
            if (!sel || sel.rangeCount === 0) return 0;
            const _range = sel.getRangeAt(0);
            const range = _range.cloneRange();
            range.selectNodeContents(event.target);
            range.setEnd(_range.endContainer, _range.endOffset);
            return range.toString().length;
        }

        function addRow () {
            const rows = table.find('tbody tr');
            let clone_index;
            if (selectedRow !== null) {
                clone_index = selectedRow;
            } else {
                clone_index = rows.length - 1;
            }
            const to_clone = rows.eq(clone_index);
            const clone = to_clone.clone(true);
            clone.find('td').html("");
            to_clone.after(clone);
            renumberRows();
            table.find('colgroup.selected').removeClass('selected');
            table.find('tr.selected').removeClass('selected');
        }

        function addCol () {
            const clone_index = selectedCol || (table.find('thead tr th').length - 1);
            const to_clone = table.find('thead tr th').eq(clone_index);
            const new_col = to_clone.clone(true);
            new_col.html(colName(clone_index + 1));
            to_clone.after(new_col);
            table.find('tbody tr').each(function () {
                const to_clone_td = $(this).find('td, th').eq(clone_index);
                const new_col_td = to_clone_td.clone(true);
                new_col_td.html("");
                to_clone_td.after(new_col_td);
            });
            table.find('colgroup').eq(clone_index).after($("<colgroup></colgroup>"));
            table.find('colgroup.selected').removeClass('selected');
            table.find('tr.selected').removeClass('selected');
        }

        function removeCol () {
            const cols = table.find('colgroup');
            if ((selectedCol !== null) && (cols.length > 2)) {
                table.find('tr').each(function () {
                    const row = $(this);
                    row.find('td, th').eq(selectedCol).remove();
                });
                cols.eq(selectedCol).remove();
            }
            table.find('colgroup.selected').removeClass('selected');
            table.find('tr.selected').removeClass('selected');
        }

        function removeRow () {
            const rows = table.find('tbody tr');
            if ((selectedRow !== null) && (rows.length > 1)) {
                rows.eq(selectedRow).remove();
            }
            renumberRows();
            table.find('colgroup.selected').removeClass('selected');
            table.find('tr.selected').removeClass('selected');
        }

        toolbar.on('click', '#table-add-row', addRow);
        toolbar.on('click', '#table-del-row', removeRow);
        toolbar.on('click', '#table-add-col', addCol);
        toolbar.on('click', '#table-del-col', removeCol);

        table.on('click', 'thead th.header', function(e){
            const colIndex = $(e.target).index();
            table.find('colgroup.selected').removeClass('selected');
            table.find('tr.selected').removeClass('selected');
            table.find('colgroup').eq(colIndex).addClass('selected');
            selectedCol = colIndex;
        });

        table.on('click', 'tbody td', function(){
            table.find('colgroup.selected').removeClass('selected');
            table.find('tr.selected').removeClass('selected');
            selectedCol = null;
            selectedRow = null;
        });

        table.on('click', 'tbody th.row-index', function(){
            table.find('colgroup.selected').removeClass('selected');
            table.find('tr.selected').removeClass('selected');
            const row = $(this).closest('tr');
            row.addClass('selected');
            selectedRow = row.index();
        });

        function setupRowNav () {
            table.on('keydown', 'tbody td', function (e) {
                const key = e.key || e.which;
                if (key === 'Enter' || key === 13) {
                    e.preventDefault();
                    let new_line = $(this).closest('tr').next().find('td');
                    if (!new_line.length) {
                        addRow();
                        new_line = table.find('tr').last().find('td');
                    }
                    if (new_line.length) new_line[0].focus();
                } else if (key === 'Tab' || key === 9) {
                    const new_line = $(this).closest('tr').next().find('td');
                    const num_cols = $(this).parent().children().length - 2;
                    if (!new_line.length && ($(this).index() === num_cols)) {
                        addRow();
                    }
                } else if (key === 'ArrowDown' || key === 40) {
                    // down arrow
                    const cur_row = $(this).closest('tr');
                    const ccol_index = $(this).index();
                    const next_row = cur_row.next();

                    if (next_row.length > 0) {
                        e.preventDefault();
                        next_row.find('th, td').eq(ccol_index).focus();
                    }
                } else if (key === 'ArrowUp' || key === 38) {
                    // up arrow
                    const cur_row = $(this).closest('tr');
                    const ccol_index = $(this).index();
                    const prev_row = cur_row.prev();

                    if (prev_row.length > 0) {
                        e.preventDefault();
                        prev_row.find('th, td').eq(ccol_index).focus();
                    }
                } else if (key === 'ArrowRight' || key === 39) {
                    // right
                    if (caret(e) === $(e.target).text().length) {
                        const next_cell = $(this).next('td');
                        if (next_cell.length > 0) {
                            e.preventDefault();
                            next_cell.focus();
                        }
                    }
                } else if (key === 'ArrowLeft' || key === 37) {
                    // left arrow
                    if (caret(e) === 0) {
                        const prev_cell = $(this).prev('td');
                        if (prev_cell.length > 0) {
                            e.preventDefault();
                            prev_cell.focus();
                        }
                    }
                }
            });
        }

        // A few jQuery helpers for exporting only
        jQuery.fn.pop = [].pop;
        jQuery.fn.shift = [].shift;

        this.exportJSON = function exportTable () {
            const data = {'headers': []};
            const info = {};

            table.find('thead .header').each(function (i) {
                const col_name = colName(i);
                const h = $(this).text().trim() || col_name;
                data['headers'].push(h);
                info[i] = [];
            });

            table.find('tbody tr').each(function (i) {
                if (i <= 1000) {  // Maximum 1000 rows
                    $(this).find('td').each(function(j) {
                        if (j <= 10) { // Maximum 10 columns
                            const value = parseFloat($(this).text()) || $(this).text().trim();
                            info[j].push(value);
                        }
                    });
                }
            });

            data['data'] = info;
            return JSON.stringify(data);
        };

        this.csv2JSON = function csv2JSON (csv) {
            const rawData = Papa.parse(csv);
            if (!rawData.data || !rawData.data.length) return;
            const headers = rawData.data[0].slice(0, 10); // Maximum 10 columns
            const result = {"headers": headers, "data": {}};

            for (let i = 1; i < Math.min(rawData.data.length, 1000); i++) {
                if (rawData.data[i].length >= headers.length) {
                    for (let j = 0; j < headers.length; j++) {
                        if (i === 1) {
                            result["data"][j] = [];
                        }
                        result["data"][j].push(rawData.data[i][j]);
                    }
                }
            }

            const details = JSON.stringify(result);
            buildTable(details);
        };

        this.xdi2JSON = function xdi2JSON (xdi) {
            const lines = xdi.split("\n");
            const meta = [];
            const data = {};
            let i = 0;
            for (i = 0; i < Math.min(1000, lines.length); i++) { // Maximum 1000 lines processed
                if (lines[i] && lines[i][0] === '#') {
                    meta.push(lines[i]);
                } else {
                    break;
                }
            }
            lines.splice(0, i);
            const lastMeta = meta.pop();
            const headers_full = lastMeta ? lastMeta.match(/\S+/g) : [];
            if (headers_full && headers_full.length) {
                headers_full.shift();
            }
            const headers = headers_full ? headers_full.slice(0, 10) : []; // Maximum 10 columns
            for (let lineIdx = 0; lineIdx < lines.length; lineIdx++) {
                const currentline = $.trim(lines[lineIdx]).match(/\S+/g);
                if (!currentline) continue;
                for (let j = 0; j < headers.length; j++) {
                    if (lineIdx === 0) {
                        data[j] = [];
                    }
                    data[j].push(currentline[j]);
                }
            }
            const details = JSON.stringify({"headers": headers, "data": data});
            buildTable(details);
        };

        function buildTable (details) {
            table.empty();
            let data;
            if (details) {
                data = JSON.parse(details);
            } else {
                data = {
                    'headers': ['A', 'B', 'C', 'D'],
                    'data': {0: [""], 1: [""], 2: [""], 3: [""]}
                };
            }

            const table_template = _.template(
                '<table class="table table-sm">' +
                '   <colgroup></colgroup>' +
                '   <% _.each(headers, function(header, i){ %>' +
                '   <colgroup></colgroup>' +
                '   <%  }); %>' +
                '   <colgroup></colgroup>' +
                '   <thead>' +
                '   <tr>' +
                '       <th></th>' +
                '       <% _.each(headers, function(header, i) { %>' +
                '           <th class="header" contenteditable="true"><%= headers[i] %></th>' +
                '       <% }); %>' +
                '   </tr>' +
                '   </thead>' +
                '   <tbody class=".sortable">' +
                '   <% for (var i=0; i < data[0].length; i++) { %>' +
                '       <tr>' +
                '           <th class="row-index"><%= (i+1) %></th>' +
                '           <% for (var h=0; h < headers.length; h++) { %>' +
                '              <td contenteditable="true"><%= data[h][i] %></td>' +
                '           <% } %>' +
                '       </tr>' +
                '   <% } %> ' +
                '   </tbody>' +
                '</table>'
            );
            table.append(table_template(data));
            const sortableInstance = sortable('.table-editable tbody', {
                forcePlaceholderSize: true,
                handle: 'th:first-child',
                items: 'tr'
            });
            if (sortableInstance && sortableInstance[0]) {
                sortableInstance[0].addEventListener('sortupdate', renumberRows);
            }
            setupRowNav();
        }

        return this;
    };
}(jQuery));

(function ( $ ) {
    $.fn.myelnCalendar = function (options) {
        // Defaults
        const settings = $.extend({
            eventSource: null,
            selectTarget: null,
            currentMonth: moment().format('YYYY-MM-DD'),
            selectedDate: null,
            target: null, // If provided, selector for calendar container
        }, options);

        // Determine containers to initialize
        // If this element has .calendar-container or is a container, use it.
        // Otherwise use settings.target or elements matching selector.
        let containers = this.filter('.calendar-container');
        if (containers.length === 0) {
            if (settings.target) {
                containers = $(settings.target);
            } else {
                containers = this.find('.calendar-container');
            }
        }
        if (containers.length === 0 && this.is('div')) {
            containers = this;
        }

        const initialReferenceMonth = moment(settings.currentMonth || moment(), 'YYYY-MM-DD');
        let currentReferenceMonth = initialReferenceMonth.clone();
        const selectedDateStr = settings.selectedDate || '';
        const monthsFetched = {};
        const eventsByDate = {};

        function getActiveQueryParams(excludeDate) {
            const params = new URLSearchParams(window.location.search);
            if (excludeDate) {
                params.delete('date');
            }
            return params;
        }

        function buildFilterDateUrl(dateStr) {
            const params = getActiveQueryParams(false);
            params.set('date', dateStr);
            const target = settings.selectTarget || window.location.pathname;
            const query = params.toString();
            return target + (query ? '?' + query : '');
        }

        function buildClearDateUrl() {
            const params = getActiveQueryParams(true);
            const target = settings.selectTarget || window.location.pathname;
            const query = params.toString();
            return target + (query ? '?' + query : '');
        }

        function fetchMonthEvents(monthMoments, callback) {
            if (!settings.eventSource) {
                if (typeof callback === 'function') callback();
                return;
            }
            const monthsToFetch = [];
            $.each(monthMoments, function(i, m) {
                const key = m.format('YYYYMM');
                if (!monthsFetched[key]) {
                    monthsToFetch.push(key);
                }
            });

            if (monthsToFetch.length === 0) {
                if (typeof callback === 'function') callback();
                return;
            }

            const queryParams = getActiveQueryParams(true);
            queryParams.set('months', monthsToFetch.join(','));

            $.ajax({
                type: 'GET',
                dataType: 'json',
                url: settings.eventSource,
                data: queryParams.toString(),
                success: function(response) {
                    if (Array.isArray(response)) {
                        $.each(response, function(idx, item) {
                            if (item.date) {
                                eventsByDate[item.date] = true;
                            }
                        });
                    }
                    $.each(monthsToFetch, function(i, key) {
                        monthsFetched[key] = true;
                    });
                    if (typeof callback === 'function') callback();
                },
                error: function() {
                    if (typeof callback === 'function') callback();
                }
            });
        }

        function renderCalendarStack(container) {
            const m3 = currentReferenceMonth.clone();
            const m2 = m3.clone().subtract(1, 'month');
            const m1 = m3.clone().subtract(2, 'month');
            const months = [m3, m2, m1];

            // Check if we are at or past the initial/latest month
            const isAtLatest = currentReferenceMonth.isSameOrAfter(initialReferenceMonth, 'month');

            const navHtml = `
                <div class="clndr-nav">
                    <button type="button" class="clndr-nav-btn clndr-prev-btn" title="Previous 3 months">
                        <i class="mi mi-chevron-left"></i>
                    </button>
                    <div class="clndr-nav-label">
                        ${m1.format('MMM YYYY')} – ${m3.format('MMM YYYY')}
                    </div>
                    <div class="d-flex align-items-center gap-1">
                        ${!isAtLatest ? `<a href="#!" class="clndr-latest-btn" title="Jump to latest month">Latest</a>` : ''}
                        <button type="button" class="clndr-nav-btn clndr-next-btn ${isAtLatest ? 'disabled' : ''}"
                                ${isAtLatest ? 'disabled' : ''} title="Next 3 months">
                            <i class="mi mi-chevron-right"></i>
                        </button>
                    </div>
                </div>
            `;

            let stackHtml = '<div class="clndr-months-stack">';
            const daysOfWeek = ['M', 'T', 'W', 'T', 'F', 'S', 'S']; // Monday first (weekOffset: 1)
            const todayStr = moment().format('YYYY-MM-DD');

            $.each(months, function(mIdx, monthMoment) {
                const monthTitle = monthMoment.format('MMMM YYYY');
                const startOfMonth = monthMoment.clone().startOf('month');
                const endOfMonth = monthMoment.clone().endOf('month');
                const totalDays = endOfMonth.date();

                // Monday is 1, Sunday is 7 in isoWeekday
                const startDay = startOfMonth.isoWeekday(); // 1 (Mon) to 7 (Sun)
                const leadingBlanks = startDay - 1;

                let monthBlockHtml = `
                    <div class="clndr-month-block" data-month="${monthMoment.format('YYYYMM')}">
                        <div class="month-header">${monthTitle}</div>
                        <div class="days-header">
                            ${daysOfWeek.map(d => `<div class="day-header">${d}</div>`).join('')}
                        </div>
                        <div class="days-grid">
                `;

                // Leading empty cells
                for (let b = 0; b < leadingBlanks; b++) {
                    monthBlockHtml += '<div class="day adjacent-month"></div>';
                }

                // Month days
                for (let d = 1; d <= totalDays; d++) {
                    const currentDayMoment = monthMoment.clone().date(d);
                    const dayIso = currentDayMoment.format('YYYY-MM-DD');
                    const isToday = (dayIso === todayStr);
                    const isSelected = (dayIso === selectedDateStr);
                    const hasEvent = !!eventsByDate[dayIso];

                    const classes = ['day'];
                    if (isToday) classes.push('today');
                    if (isSelected) classes.push('selected');
                    if (hasEvent) classes.push('has-event');

                    monthBlockHtml += `<div class="${classes.join(' ')}" data-date="${dayIso}" title="${currentDayMoment.format('MMM D, YYYY')}${hasEvent ? ' (Entries)' : ''}">${d}</div>`;
                }

                // Trailing empty cells to fill the row
                const trailingBlanks = (7 - ((leadingBlanks + totalDays) % 7)) % 7;
                for (let a = 0; a < trailingBlanks; a++) {
                    monthBlockHtml += '<div class="day adjacent-month"></div>';
                }

                monthBlockHtml += `
                        </div>
                    </div>
                `;
                stackHtml += monthBlockHtml;
            });
            stackHtml += '</div>';

            const contents = container.find('.contents').length ? container.find('.contents') : container;
            contents.html(navHtml + stackHtml);

            // Bind click handlers
            contents.find('.clndr-prev-btn').off('click').on('click', function(e) {
                e.preventDefault();
                currentReferenceMonth.subtract(3, 'months');
                updateAll();
            });

            contents.find('.clndr-next-btn').off('click').on('click', function(e) {
                e.preventDefault();
                if (currentReferenceMonth.isBefore(initialReferenceMonth, 'month')) {
                    currentReferenceMonth.add(3, 'months');
                    if (currentReferenceMonth.isAfter(initialReferenceMonth, 'month')) {
                        currentReferenceMonth = initialReferenceMonth.clone();
                    }
                    updateAll();
                }
            });

            contents.find('.clndr-latest-btn').off('click').on('click', function(e) {
                e.preventDefault();
                currentReferenceMonth = initialReferenceMonth.clone();
                updateAll();
            });

            contents.find('.day.has-event').off('click').on('click', function(e) {
                e.preventDefault();
                const clickedDate = $(this).data('date');
                if (clickedDate === selectedDateStr) {
                    // Clicking currently selected date toggles/clears the filter
                    window.location.href = buildClearDateUrl();
                } else {
                    window.location.href = buildFilterDateUrl(clickedDate);
                }
            });
        }

        function updateAll() {
            const m3 = currentReferenceMonth.clone();
            const m2 = m3.clone().subtract(1, 'month');
            const m1 = m3.clone().subtract(2, 'month');
            fetchMonthEvents([m1, m2, m3], function() {
                containers.each(function() {
                    renderCalendarStack($(this));
                });
            });
        }

        // Initial render
        updateAll();

        return this;
    };

}(jQuery));

// Notebook Annotations Controller
const NotebookAnnotations = {
    activePopover: null,
    activeEntry: null,
    activeQuote: null,

    getCsrfToken: function() {
        return getCsrfToken();
    },

    escapeHtml: function(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    },

    formatTime: function(isoString) {
        if (!isoString) return '';
        if (window.moment) {
            return moment(isoString).fromNow();
        }
        return isoString;
    },

    init: function(containerSelector) {
        const self = this;
        const root = $(containerSelector || '#notebook-content');

        // Text selection handling to open comment popover
        root.on('mouseup touchend', '.notebook-entry', function(e) {
            // Ignore mouseups on interactive controls or inside active popovers
            if ($(e.target).closest('.entry-tools, .entry-comment-badge, .tag-cloud, .popover, .btn, a, input, textarea').length) {
                return;
            }

            const selection = (window.getSelection ? window.getSelection().toString() : '').trim();
            if (!selection) {
                return;
            }

            const entry = $(this);
            self.showCreatePopover(entry, selection, e);
        });

        // Comment badge button toggle
        root.on('click', '.entry-comment-badge', function(e) {
            e.preventDefault();
            e.stopPropagation();
            const badgeBtn = $(this);
            self.toggleCommentsPopover(badgeBtn);
        });

        // Close active popover when clicking outside
        $(document).on('mousedown touchstart', function(e) {
            if (self.activePopover) {
                const popoverEl = document.querySelector('.annotation-popover.show, .entry-comments-popover.show');
                if (popoverEl && (popoverEl.contains(e.target) || $(e.target).closest('.entry-comment-badge').length)) {
                    return;
                }
                self.disposeActivePopover();
            }
        });
    },

    disposeActivePopover: function() {
        if (this.activePopover) {
            try {
                this.activePopover.dispose();
            } catch (err) {
                // Ignore already disposed popover errors
            }
            this.activePopover = null;
        }
        this.activeEntry = null;
        this.activeQuote = null;
    },

    showCreatePopover: function(entry, quote, event) {
        const self = this;
        self.disposeActivePopover();

        const annotateUrl = entry.data('annotate-url');
        if (!annotateUrl) return;

        self.activeEntry = entry;
        self.activeQuote = quote;

        // Position helper element or anchor to target
        const targetEl = event.target || entry[0];

        const formHtml = `
            <div class="annotation-create-card p-2" style="min-width: 240px; max-width: 320px;">
                <div class="mb-2 text-muted small fst-italic text-truncate" title="${self.escapeHtml(quote)}">
                    "${self.escapeHtml(quote)}"
                </div>
                <div class="mb-2">
                    <textarea class="form-control form-control-sm annotation-text-input" rows="3" placeholder="Add a comment..."></textarea>
                </div>
                <div class="d-flex justify-content-end gap-2">
                    <button type="button" class="btn btn-sm btn-outline-secondary btn-cancel-annotation">Cancel</button>
                    <button type="button" class="btn btn-sm btn-primary btn-submit-annotation">Save</button>
                </div>
            </div>
        `;

        const popover = new bootstrap.Popover(targetEl, {
            trigger: 'manual',
            html: true,
            placement: 'bottom',
            fallbackPlacement: ['top'],
            customClass: 'annotation-popover shadow-sm',
            container: 'body',
            content: formHtml,
            sanitize: false
        });

        popover.show();
        self.activePopover = popover;

        const popoverTip = popover.getTipElement ? popover.getTipElement() : document.querySelector('.annotation-popover.show');
        if (popoverTip) {
            const input = popoverTip.querySelector('.annotation-text-input');
            if (input) input.focus();

            $(popoverTip).find('.btn-cancel-annotation').on('click', function() {
                self.disposeActivePopover();
            });

            $(popoverTip).find('.btn-submit-annotation').on('click', function() {
                const text = $(input).val();
                self.submitAnnotation(entry, text, quote);
            });

            $(input).on('keydown', function(e) {
                if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                    e.preventDefault();
                    self.submitAnnotation(entry, $(input).val(), quote);
                }
            });
        }
    },

    submitAnnotation: function(entry, text, quote) {
        const self = this;
        const trimmedText = (text || '').trim();
        if (!trimmedText) {
            return;
        }

        const annotateUrl = entry.data('annotate-url');
        if (!annotateUrl) return;

        $.ajax({
            type: 'POST',
            url: annotateUrl,
            contentType: 'application/json',
            data: JSON.stringify({
                text: trimmedText,
                quote: quote || ''
            }),
            beforeSend: function(xhr) {
                xhr.setRequestHeader('X-CSRFToken', self.getCsrfToken());
            },
            success: function(response) {
                self.disposeActivePopover();
                self.appendAnnotationData(entry, response, true);
                if (response.quote) {
                    self.markQuote(entry, response.quote, response.id);
                }
                self.updateCommentBadge(entry, 1);
            },
            error: function(xhr) {
                alert(xhr.responseJSON && xhr.responseJSON.error ? xhr.responseJSON.error : 'Failed to save annotation.');
            }
        });
    },

    deleteAnnotation: function(entry, annId, popoverInstance) {
        const self = this;
        const annotateUrl = entry.data('annotate-url');
        if (!annotateUrl) return;

        const deleteUrl = annotateUrl.endsWith('/') ? `${annotateUrl}${annId}/` : `${annotateUrl}/${annId}/`;

        $.ajax({
            type: 'DELETE',
            url: deleteUrl,
            beforeSend: function(xhr) {
                xhr.setRequestHeader('X-CSRFToken', self.getCsrfToken());
            },
            success: function() {
                // Remove script tag
                entry.find(`#annotation-${annId}`).remove();

                // Re-mark entry to update highlights
                self.markEntry(entry);

                // Decrement count
                self.updateCommentBadge(entry, -1);

                // Refresh comments popover if open
                if (popoverInstance) {
                    self.refreshCommentsPopover(entry, popoverInstance);
                }
            },
            error: function() {
                alert('Failed to delete annotation.');
            }
        });
    },

    appendAnnotationData: function(entry, data, isAuthor) {
        let container = entry.find('.annotations-data');
        if (!container.length) {
            entry.append('<div class="annotations-data" hidden></div>');
            container = entry.find('.annotations-data');
        }
        const scriptEl = $(document.createElement('script'))
            .attr('id', `annotation-${data.id}`)
            .attr('type', 'application/json')
            .attr('data-pk', data.id)
            .attr('data-isauthor', isAuthor ? 'true' : 'false')
            .text(JSON.stringify(data));
        container.append(scriptEl);
    },

    getEntryAnnotations: function(entry) {
        const annotations = [];
        entry.find('.annotations-data script[type="application/json"]').each(function() {
            try {
                const item = JSON.parse($(this).text());
                item.isAuthor = $(this).attr('data-isauthor') === 'true';
                annotations.push(item);
            } catch (e) {
                // ignore parsing errors
            }
        });
        return annotations;
    },

    updateCommentBadge: function(entry, delta) {
        const badge = entry.find('.entry-comment-badge .comment-count');
        if (!badge.length) return;

        let current = parseInt(badge.text(), 10) || 0;
        let next = Math.max(0, current + delta);
        badge.text(next);

        if (next > 0) {
            badge.removeClass('bg-transparent text-muted').addClass('bg-secondary text-white');
        } else {
            badge.removeClass('bg-secondary text-white').addClass('bg-transparent text-muted');
        }
    },

    toggleCommentsPopover: function(badgeBtn) {
        const self = this;
        const entry = badgeBtn.closest('.notebook-entry');

        if (self.activePopover) {
            const isSame = self.activeEntry && self.activeEntry[0] === entry[0];
            self.disposeActivePopover();
            if (isSame) {
                return;
            }
        }

        const annotations = self.getEntryAnnotations(entry);
        let contentHtml = '';

        if (!annotations.length) {
            contentHtml = '<div class="p-3 text-muted text-center small">No comments yet.</div>';
        } else {
            let itemsHtml = '';
            annotations.forEach(function(ann) {
                const quoteBlock = ann.quote ? `<div class="comment-quote">"${self.escapeHtml(ann.quote)}"</div>` : '';
                const deleteBtn = ann.isAuthor ? `
                    <button type="button" class="btn btn-link btn-sm p-0 comment-delete-btn" data-pk="${ann.id}" title="Delete comment">
                        <i class="mi mi-trash"></i>
                    </button>` : '';

                itemsHtml += `
                    <div class="comment-item" data-pk="${ann.id}">
                        ${quoteBlock}
                        <div class="comment-meta">
                            <span class="fw-bold">${self.escapeHtml(ann.author)}</span>
                            <div class="d-flex align-items-center gap-1">
                                <span>${self.formatTime(ann.created)}</span>
                                ${deleteBtn}
                            </div>
                        </div>
                        <div class="comment-text">${self.escapeHtml(ann.text)}</div>
                    </div>
                `;
            });
            contentHtml = `<div class="entry-comments-card">${itemsHtml}</div>`;
        }

        const popover = new bootstrap.Popover(badgeBtn[0], {
            trigger: 'manual',
            html: true,
            placement: 'bottom',
            fallbackPlacement: ['top'],
            customClass: 'entry-comments-popover shadow-sm',
            container: 'body',
            content: contentHtml,
            sanitize: false
        });

        popover.show();
        self.activePopover = popover;
        self.activeEntry = entry;

        self.bindCommentsPopoverEvents(entry, popover);
    },

    refreshCommentsPopover: function(entry, popoverInstance) {
        const self = this;
        const annotations = self.getEntryAnnotations(entry);
        if (!annotations.length) {
            self.disposeActivePopover();
            return;
        }

        let itemsHtml = '';
        annotations.forEach(function(ann) {
            const quoteBlock = ann.quote ? `<div class="comment-quote">"${self.escapeHtml(ann.quote)}"</div>` : '';
            const deleteBtn = ann.isAuthor ? `
                <button type="button" class="btn btn-link btn-sm p-0 comment-delete-btn" data-pk="${ann.id}" title="Delete comment">
                    <i class="mi mi-trash"></i>
                </button>` : '';

            itemsHtml += `
                <div class="comment-item" data-pk="${ann.id}">
                    ${quoteBlock}
                    <div class="comment-meta">
                        <span class="fw-bold">${self.escapeHtml(ann.author)}</span>
                        <div class="d-flex align-items-center gap-1">
                            <span>${self.formatTime(ann.created)}</span>
                            ${deleteBtn}
                        </div>
                    </div>
                    <div class="comment-text">${self.escapeHtml(ann.text)}</div>
                </div>
            `;
        });

        const popoverTip = popoverInstance.getTipElement ? popoverInstance.getTipElement() : document.querySelector('.entry-comments-popover.show');
        if (popoverTip) {
            const body = popoverTip.querySelector('.popover-body');
            if (body) {
                body.innerHTML = `<div class="entry-comments-card">${itemsHtml}</div>`;
                self.bindCommentsPopoverEvents(entry, popoverInstance);
            }
        }
    },

    bindCommentsPopoverEvents: function(entry, popoverInstance) {
        const self = this;
        const popoverTip = popoverInstance.getTipElement ? popoverInstance.getTipElement() : document.querySelector('.entry-comments-popover.show');
        if (!popoverTip) return;

        $(popoverTip).find('.comment-delete-btn').on('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            const annId = $(this).data('pk');
            if (confirm('Are you sure you want to delete this comment?')) {
                self.deleteAnnotation(entry, annId, popoverInstance);
            }
        });
    },

    markQuote: function(entry, quote, annId) {
        if (!quote || !entry.mark) return;
        entry.mark(quote, {
            caseSensitive: true,
            ignoreJoiners: true,
            className: 'annotation-quote',
            acrossElements: true,
            separateWordSearch: false,
            each: function(mark) {
                if (annId) {
                    $(mark).attr('data-ann-pk', annId);
                }
            }
        });
    },

    markEntry: function(entry) {
        const self = this;
        const $entry = $(entry);
        if ($entry.unmark) {
            $entry.unmark({ className: 'annotation-quote' });
        }

        const annotations = self.getEntryAnnotations($entry);
        annotations.forEach(function(ann) {
            if (ann.quote) {
                self.markQuote($entry, ann.quote, ann.id);
            }
        });
    }
};

(function($) {
    $.fn.annotate = function(entry_selector) {
        NotebookAnnotations.init(this);
        return this;
    };
})(jQuery);



//tags
function editTags(elem){
    const content = $('#notebook-content');
    const button = $(elem);
    const entry = button.closest('.notebook-entry');
    const initial = button.data('tags') || '';

    MyelnNotebooks.tags = {
        entry_id: entry.data('entry-pk'),
        url: button.data('url'),
    };

    const width = Math.max($(content).width(), 300) * 0.8;

    const template = (
        '<div class="comment-form" tabindex="-1">' +
        '    <textarea id="tag-input" rows="3" cols="30" name="text" ' +
        '       class="form-control input-md" ' +
        '       placeholder="Enter comma-separated list of keywords ...">' + initial + '</textarea>' +
        '    <div class="w-100 comment-form-tools">' +
        '       <i class="mi mi-tags mi-fw"></i>' +
        '       <button type="button" title="Cancel" onclick="cancelTags();" class="btn btn-sm btn-light ms-auto me-3"><i class="mi mi-cross"></i>' +
        '       </button>' +
        '       <button type="button" title="Save" onclick="submitTags();" class="btn btn-sm btn-success"><i class="mi mi-save"></i>' +
        '       </button>' +
        '    </div>' +
        '</div>'
    );

    MyelnNotebooks.popover = button;
    showPopover(button, {
        trigger: "click",
        html: true,
        container: 'body',
        placement: "bottom",
        fallbackPlacement: ['top'],
        content: template,
        template: (
            '<div class="popover form menu" role="tooltip">' +
            '   <div class="popover-arrow arrow"></div>' +
            '   <div class="popover-body"></div>' +
            '</div>'
        )
    });

    $('#tag-input').focus();
}

function cancelTags() {
    if (MyelnNotebooks.popover) {
        disposePopover(MyelnNotebooks.popover);
        MyelnNotebooks.popover = null;
        MyelnNotebooks.tags = null;
    }
}

function submitTags() {
    if (MyelnNotebooks.tags) {
        const tags = MyelnNotebooks.tags;
        const text = $('#tag-input').val();

        if (!text) {
            disposePopover(MyelnNotebooks.popover);
            MyelnNotebooks.popover = null;
            MyelnNotebooks.tags = null;
            return;
        }

        $.ajax({
            type: 'POST',
            url: tags.url,
            data: {
                'pk': tags.entry_id,
                'tags': text,
            },
            beforeSend: function(xhr, settings){
                disposePopover(MyelnNotebooks.popover);
                MyelnNotebooks.popover = null;
                MyelnNotebooks.tags = null;
                xhr.setRequestHeader("X-CSRFToken", getCsrfToken());
            },
            success: function(response) {
                const selector = '#entry-'+tags.entry_id;
                disposeTooltips(selector);
                $(selector).replaceWith(response);
                initEntries(selector);
            }
        });
    }
}


function loadIndex(element, height) {
    const $index = $('#notebook-index');
    if (!$index.length) return;
    const url = element.data('index-url');
    if (!url) return;

    const active = $index.find('#index-' + element.data("entry-pk"));
    const index = $index.find('.index');

    $index.find('.active').removeClass('active');
    active.addClass('active');

    const num_visible = Math.round(height / 50);

    if (!MyelnNotebooks.index_loading) {
        MyelnNotebooks.index_loading = true;
        $.ajax({
            type: 'GET',
            url: url,
            data: {
                'load': num_visible,
                'active': element.data("entry-pk")
            },
            success: function(response) {
                const source = $('' + response + '');
                const indexContainer = $index.find('.index');

                let end = false;
                const first_entry = indexContainer.children().first();
                $(source).children().each(function() {
                    const el = indexContainer.find('#index-' + $(this).data('entry-pk'));
                    if (el.length) {
                        end = true;
                    } else {
                        if (!end) {
                            first_entry.before($(this));
                        } else {
                            indexContainer.append($(this));
                        }
                    }
                });
                const i = indexContainer.find('.active').index();

                const vis_above = (num_visible - num_visible % 2) / 2;
                const vis_below = (num_visible + num_visible % 2) / 2 - 1;

                const loaded_below = indexContainer.children().length - (i + 1);
                let offset = i - vis_above;
                if (vis_below > loaded_below) {
                    offset = offset - (vis_below - loaded_below);
                }
                indexContainer.animate({
                    marginTop: -1 * (offset * 50),
                }, 250);

                MyelnNotebooks.index_loading = false;
            },
            error: function() {
                MyelnNotebooks.index_loading = false;
            }
        });
    }
}

function checkLoading(t) {
    return new Promise(function(resolve) {
        const interval = setInterval(function(){
            if (!MyelnNotebooks.loading) {
               resolve();
               clearInterval(interval);
            }
        }, t);
    });
}

MyelnNotebooks.lastViewTop = 0;

function initEntries(selector) {
    $(selector).each(function(){
        // Math Katex
        if (typeof renderMathInElement === 'function') {
            renderMathInElement(this);
        }

        // tooltips - supports Bootstrap 5 and Bootstrap 4 fallback
        $(this).find('[data-bs-toggle="tooltip"], [title]').each(function() {
            if (window.bootstrap && bootstrap.Tooltip) {
                bootstrap.Tooltip.getOrCreateInstance(this);
            } else if ($.fn.tooltip) {
                $(this).tooltip();
            }
        });

        // Annotations
        NotebookAnnotations.markEntry(this);

        // Data plotting tab - support both BS5 data-bs-toggle and BS4 data-toggle
        $(this).find('a.plot-tab[data-bs-toggle="tab"], a.plot-tab[data-toggle="tab"]').on('shown.bs.tab', function(e){
            plotData(e.target);
        });
    });
}

function draw_xy_chart() {
    let width = 600;
    let height = 300;
    let xlabel = '';
    let y1label = '';
    let y2label = '';
    let xscale = 'linear';
    let scatter = 'scatter';
    let interpolation = 'linear';
    let binning = 50;
    let timeformat = null;

    function chart(selection) {
        selection.each(function (datasets) {
            const xoffset = 0;
            const bmargin = xlabel ? 50 : 20;
            const margin = {top: 20, right: width * 0.1, bottom: bmargin, left: width * 0.1};
            const innerwidth = width - margin.left - margin.right;
            const innerheight = height - margin.top - margin.bottom;

            const svg = d3.select(this)
                .attr("width", width)
                .attr("height", height)
                .append("g")
                .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

            const color_scale = d3.scaleOrdinal(d3.schemeCategory10);
            let y1data = [];
            let y2data = [];
            const y1datasets = [];
            const y2datasets = [];
            let x_scale;
            let y1_scale;
            let y2_scale;
            let bins;
            let color;
            let xmin;
            let xmax;

            if (scatter === 'bar') {
                color = datasets['color'];
                xmin = d3.min(datasets.data);
                xmax = d3.max(datasets.data);
                switch (xscale) {
                    case 'time':
                        x_scale = d3.scaleTime()
                            .range([0, innerwidth])
                            .domain([xmin, xmax]);
                        break;
                    case 'linear':
                    default:
                        x_scale = d3.scaleLinear()
                            .range([0, innerwidth])
                            .domain([xmin, xmax]);
                        break;
                }
                bins = d3.histogram()
                    .value(function (d) { return d; })
                    .domain([d3.min(datasets.data), d3.max(datasets.data)])
                    .thresholds(x_scale.ticks(binning))(datasets['data']);
                y1_scale = d3.scaleLinear()
                    .domain([0, d3.max(bins, function (d) { return d.length; })])
                    .range([innerheight, 0]);
            } else {
                xmin = d3.min(datasets, function (d) { return d3.min(d.x); });
                xmax = d3.max(datasets, function (d) { return d3.max(d.x); });
                switch (xscale) {
                    case 'inv-square':
                        x_scale = d3.scalePow().exponent(-2)
                            .range([0, innerwidth])
                            .domain([xmax, xmin]);
                        break;
                    case 'pow':
                        x_scale = d3.scalePow()
                            .range([0, innerwidth])
                            .domain([xmin, xmax]);
                        break;
                    case 'log':
                        x_scale = d3.scaleLog()
                            .range([0, innerwidth])
                            .domain([xmin, xmax]);
                        break;
                    case 'identity':
                        x_scale = d3.scaleIdentity()
                            .range([0, innerwidth])
                            .domain([xmin, xmax]);
                        break;
                    case 'time':
                        x_scale = d3.scaleTime()
                            .range([0, innerwidth])
                            .domain([xmin, xmax]);
                        break;
                    case 'inverse':
                        x_scale = d3.scaleLinear()
                            .range([0, innerwidth])
                            .domain([xmax, xmin]);
                        break;
                    case 'linear':
                    default:
                        x_scale = d3.scaleLinear()
                            .range([0, innerwidth])
                            .domain([xmin, xmax]);
                        break;
                }

                let fit = d3.curveLinear;
                switch(interpolation) {
                    case 'cardinal':
                        fit = d3.curveCardinal;
                        break;
                    case 'step':
                        fit = d3.curveStep;
                        break;
                    case 'step-after':
                        fit = d3.curveStepAfter;
                        break;
                    case 'step-before':
                        fit = d3.curveStepBefore;
                        break;
                    case 'basis':
                        fit = d3.curveBasis;
                        break;
                    case 'linear':
                    default:
                        fit = d3.curveLinear;
                        break;
                }

                for (let p = 0; p < datasets.length; p++) {
                    datasets[p]['color'] = color_scale(p);
                    if (datasets[p]['y1']) {
                        y1data = y1data.concat(datasets[p]['y1']);
                        y1datasets.push(datasets[p]);
                    }
                    if (datasets[p]['y2']) {
                        y2data = y2data.concat(datasets[p]['y2']);
                        y2datasets.push(datasets[p]);
                    }
                }

                y1_scale = d3.scaleLinear()
                    .range([innerheight - xoffset, 0])
                    .domain([d3.min(y1data), d3.max(y1data)]);

                y2_scale = d3.scaleLinear()
                    .range([innerheight - xoffset, 0])
                    .domain([d3.min(y2data), d3.max(y2data)]);
            }

            const x_axis = d3.axisBottom()
                .scale(x_scale)
                .tickSize(-innerheight);
            if (xscale === 'inv-square') {
                if (typeof inv_sqrt === 'function' && Array.cleanspace) {
                    const ticks = inv_sqrt(Array.cleanspace(Math.pow(xmax, -2), Math.pow(xmin, -2), 8));
                    x_axis.tickValues(ticks).tickFormat(d3.format(".3"));
                }
            } else if (xscale === 'time' && timeformat) {
                x_axis.ticks(7).tickFormat(d3.timeFormat(timeformat));
            }

            const y1_axis = d3.axisLeft()
                .scale(y1_scale)
                .tickSize(-innerwidth);

            const y2_axis = d3.axisRight()
                .scale(y2_scale);

            svg.append("g")
                .attr("class", "x axis")
                .attr("transform", "translate(0," + innerheight + ")")
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
                .attr("fill", function () {
                    if (y1datasets.length > 1 || !y1datasets.length) {
                        return "#000000";
                    }
                    return y1datasets[0]['color'];
                })
                .text(y1label);

            if (scatter === 'bar') {
                const bar = svg.selectAll(".bar")
                    .data(bins)
                    .enter().append("g")
                    .attr("class", "bar")
                    .attr("fill", color)
                    .attr("transform", function(d) { return "translate(" + x_scale(d.x0) + "," + y1_scale(d.length) + ")"; });

                bar.append("rect")
                    .attr("x", 1)
                    .attr("title", function(d) {
                        if (xscale === 'time' && timeformat) {
                            return d3.timeFormat(timeformat)(d.x0) + '-' + d3.timeFormat(timeformat)(d.x1) + ': ' + d.length + ' entries';
                        } else {
                            return d.x0 + '-' + d.x1 + ': ' + d.length + ' entries';
                        }
                    })
                    .attr("width", x_scale(bins[0].x1) - (Math.max(0, x_scale(bins[0].x0) - 1)))
                    .attr("height", function(d) { return innerheight - y1_scale(d.length); });

            } else {
                const y1_draw_line = [];
                const y2_draw_line = [];

                for (let p = 0; p < datasets.length; p++) {
                    if (datasets[p]['y1']) {
                        y1_draw_line.push(d3.line()
                            .curve(fit)
                            .x(function (d) { return x_scale(d[0]); })
                            .y(function (d) { return y1_scale(d[1]); }));
                    } else if (datasets[p]['y2']) {
                        y2_draw_line.push(d3.line()
                            .curve(fit)
                            .x(function (d) { return x_scale(d[0]); })
                            .y(function (d) { return y2_scale(d[1]); }));
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
                        .attr("fill", function () {
                            if (y2datasets.length > 1) {
                                return "#000000";
                            }
                            return y2datasets[0]['color'];
                        })
                        .text(y2label);
                }

                const y1_data_lines = svg.selectAll(".d3_xy1_chart_line")
                    .data(y1datasets.map(function (d) { return d3.zip(d.x, d.y1); }))
                    .enter().append("g")
                    .attr("class", "d3_xy1_chart_line");
                const y2_data_lines = svg.selectAll(".d3_xy2_chart_line")
                    .data(y2datasets.map(function (d) { return d3.zip(d.x, d.y2); }))
                    .enter().append("g")
                    .attr("class", "d3_xy2_chart_line");

                for (let p = 0; p < y1_draw_line.length; p++) {
                    if (scatter === 'line') {
                        y1_data_lines.append("path")
                            .attr("class", "line")
                            .attr("d", function (d) { return y1_draw_line[p](d); })
                            .attr("data-legend", function (_, l) { return y1datasets[l]['label'] || null; })
                            .attr("stroke", function (_, l) { return y1datasets[l]['color']; })
                            .attr("fill", "none");
                    } else {
                        for (let k = 0; k < y1datasets.length; k++) {
                            const newdata = y1datasets[k]['x'].map(function (e, j) {
                                return [e, y1datasets[k]['y1'][j]];
                            });
                            svg.selectAll("dot")
                                .data(newdata)
                                .enter().append("circle")
                                .attr("r", 2)
                                .attr("cx", function (d) { return x_scale(d[0]); })
                                .attr("cy", function (d) { return y1_scale(d[1]); })
                                .attr("fill", function () { return y1datasets[k]['color']; });
                        }
                    }
                }

                for (let p = 0; p < y2_draw_line.length; p++) {
                    if (scatter === 'line') {
                        y2_data_lines.append("path")
                            .attr("class", "line")
                            .attr("d", function (d) { return y2_draw_line[p](d); })
                            .attr("data-legend", function (_, l) { return y2datasets[l]['label'] || null; })
                            .attr("stroke", function (_, l) { return y2datasets[l]['color']; })
                            .attr("fill", "none");
                    } else {
                        for (let k = 0; k < y2datasets.length; k++) {
                            const newdata = y2datasets[k]['x'].map(function (e, j) {
                                return [e, y2datasets[k]['y2'][j]];
                            });
                            svg.selectAll("dot")
                                .data(newdata)
                                .enter().append("circle")
                                .attr("r", 2)
                                .attr("cx", function (d) { return x_scale(d[0]); })
                                .attr("cy", function (d) { return y2_scale(d[1]); })
                                .attr("fill", function () { return y2datasets[k]['color']; });
                        }
                    }
                }

                const legend = svg.append("g")
                    .attr("class", "legend")
                    .attr("transform", "translate(50,30)");
                if (d3.legend) {
                    legend.call(d3.legend);
                }

                /* Interactive stuff */
                const mouseG = svg.append("g")
                    .attr("class", "mouse-over-effects");

                mouseG.append("path")
                    .attr("class", "mouse-line")
                    .style("stroke", "#333")
                    .style("stroke-width", "0.5px")
                    .style("opacity", "0");

                let mousePerLine;
                if (y2datasets.length) {
                    const dualdatasets = [];
                    for (let p = 0; p < y1datasets.length; p++) {
                        dualdatasets.push({'x': y1datasets[p]['x'], 'y1': y1datasets[p]['y1']});
                    }
                    for (let p = 0; p < y2datasets.length; p++) {
                        dualdatasets.push({'x': y2datasets[p]['x'], 'y1': y2datasets[p]['y2'], 'scale': y2_scale});
                    }
                    mousePerLine = mouseG.selectAll('.mouse-per-line')
                        .data(dualdatasets)
                        .enter()
                        .append("g")
                        .attr("class", "mouse-per-line");
                } else {
                    mousePerLine = mouseG.selectAll('.mouse-per-line')
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

                const mouseX = svg.append("text")
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
                    .on('mouseover', function () {
                        svg.select(".mouse-line").style("opacity", "1");
                        svg.selectAll(".mouse-per-line circle").style("opacity", "1");
                        svg.selectAll(".mouse-per-line text").style("opacity", "1");
                        mouseX.style("opacity", "1");
                    })
                    .on('mousemove', function () {
                        const mouse = d3.mouse(this);
                        svg.select(".mouse-line")
                            .attr("d", function () {
                                return "M" + mouse[0] + "," + innerheight + " " + mouse[0] + ",0";
                            });
                        svg.selectAll(".mouse-per-line")
                            .style("stroke", function (d, n) {
                                return color_scale(n);
                            })
                            .attr("transform", function (d) {
                                const xPos = x_scale.invert(mouse[0]);
                                mouseX.text("X = " + xPos.toFixed(2));
                                const closest = d['x'].reduce(function (prev, curr) {
                                    return (Math.abs(curr - xPos) < Math.abs(prev - xPos) ? curr : prev);
                                });
                                const i = d['x'].indexOf(closest);

                                const scale = d['scale'] || y1_scale;
                                const pos = scale(d['y1'][i]);
                                d3.select(this).select('text')
                                    .style("stroke", "none")
                                    .text(scale.invert(pos).toFixed(2));
                                return "translate(" + x_scale(closest) + "," + pos + ")";
                            });
                    });
                /* End of interactive stuff */
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
    chart.interpolation = function (value) {
        if (!arguments.length) return interpolation;
        interpolation = value;
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

function drawStackChart(data, label, canvasStackChart, colorStackChart, xStackChart, yStackChart, heightStackChart) {

    colorStackChart.domain(d3.keys(data[0]).filter(function (key) { return key !== label && key !== 'color'; }));

    data.forEach(function (d) {
        let y0 = 0;
        d.ages = colorStackChart.domain().map(function (name) {
            return {
                name: name,
                y0: y0,
                y1: y0 += +d[name],
                color: d['color'] || null,
                label: d[label]
            };
        });
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
        .attr("x", -10)
        .attr("dy", ".35em")
        .attr("transform", "rotate(-45)")
        .style("text-anchor", "end");

    const state = canvasStackChart.selectAll("." + label)
        .data(data)
        .enter().append("g")
        .attr("class", "g")
        .attr("transform", function (d) { return "translate(" + xStackChart(d[label]) + ",0)"; });

    let yaxis = canvasStackChart.append("g")
        .attr("class", "y axis")
        .call(d3.axisLeft(yStackChart));

    let active_link = "0";
    let legendClassArray = [];
    const legend = canvasStackChart.selectAll(".legend")
        .data(colorStackChart.domain().slice().reverse())
        .enter().append("g")
        .attr("class", function (d) {
            legendClassArray.push(d.replace(/\s/g, ''));
            return "legend";
        })
        .attr("transform", function(d, i) { return "translate(20," + (i * 20) + ")"; });

    // reverse order to match order in which bars are stacked
    legendClassArray = legendClassArray.reverse();

    state.selectAll("rect")
        .data(function (d) { return d.ages; })
        .enter().append("rect")
        .attr("width", xStackChart.bandwidth())
        .attr("class", function(d, i) { return 'class' + legendClassArray[i]; })
        .attr("title", function(d, i) { return legendClassArray[i] + ' (' + d.label + '): ' + (d.y1 - d.y0); })
        .attr("y", function (d) { return yStackChart(d.y1); })
        .attr("height", function (d) { return yStackChart(d.y0) - yStackChart(d.y1); })
        .style("fill", function (d) { return d.color || colorStackChart(d.name); })
        .style("opacity", function (d, i) { return d.color ? 1 - ((0.75 / legendClassArray.length) * i) : 1; });

    let y_orig = [];
    let h_orig = [];
    let ySingleChart;

    if (legendClassArray.length > 1) {
        legend.append("circle")
            .attr("cy", 9)
            .attr("r", 9)
            .style("fill", colorStackChart)
            .attr("id", function (d) {
                return "id" + d.replace(/\s/g, '');
            })
            .on("mouseover", function () {
                if (active_link === "0") {
                    d3.select(this).style("cursor", "pointer");
                } else {
                    if (active_link.split("class").pop() === this.id.split("id").pop()) {
                        d3.select(this).style("cursor", "pointer");
                    } else {
                        d3.select(this).style("cursor", "auto");
                    }
                }
            })
            .on("click", function () {
                const active_id = '#id' + active_link;
                d3.select(active_id).style("stroke", "none");
                if (active_link !== this.id.split("id").pop()) {
                    if (active_link !== "0") {
                        restorePlot($(active_id)[0], 1, 1);
                    }
                    d3.select(this)
                        .style("stroke", "black")
                        .style("stroke-width", 2);

                    active_link = this.id.split("id").pop();
                    plotSingle(this);
                } else {
                    restorePlot($(active_id)[0], 500, 100);
                    active_link = "0";
                }
            });

        legend.append("text")
            .attr("x", 24)
            .attr("y", 9)
            .attr("dy", ".35em")
            .style("text-anchor", "start")
            .text(function (d) { return d; });
    }

    function restorePlot(d, duration, delay) {
        duration = duration || 500;
        delay = delay || 100;
        if (!d) return;
        const class_keep = d.id.split("id").pop();
        const idx = legendClassArray.indexOf(class_keep);

        $.each(state.selectAll("rect"), function (i, e) {
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

        // restore opacity of erased bars
        for (let i = 0; i < legendClassArray.length; i++) {
            if (legendClassArray[i] !== class_keep) {
                state.selectAll(".class" + legendClassArray[i])
                    .transition()
                    .duration(duration)
                    .delay(delay)
                    .style('display', 'block');
            }
        }
        yaxis.remove();
        yaxis = canvasStackChart.append("g")
            .attr("class", "y axis")
            .call(d3.axisLeft(yStackChart));
    }

    function plotSingle(d) {
        const class_keep = d.id.split("id").pop();
        const idx = legendClassArray.indexOf(class_keep);
        let key_keep = class_keep;
        $.each(data[0], function(k) {
            if (k.replace(/\s/g, '') === class_keep) {
                key_keep = k;
                return false;
            }
        });
        ySingleChart = d3.scaleLinear().range([heightStackChart, 0]).domain([0, d3.max(data, function (item) { return item[key_keep]; })]);

        yaxis.remove();
        yaxis = canvasStackChart.append("g")
            .attr("class", "y axis")
            .call(d3.axisLeft(ySingleChart));

        for (let i = 0; i < legendClassArray.length; i++) {
            if (legendClassArray[i] !== class_keep) {
                state.selectAll(".class" + legendClassArray[i])
                    .transition()
                    .duration(500)
                    .style("display", "none");
            }
        }

        y_orig = [];
        h_orig = [];
        $.each(state.selectAll("rect"), function (i, rectGroup) {
            $.each(rectGroup, function(j, r) {
                if (r[idx]) {
                    const h_keep = d3.select(r[idx]).attr("height");
                    const y_keep = d3.select(r[idx]).attr("y");
                    y_orig.push(y_keep);
                    h_orig.push(h_keep);

                    const h_base = d3.select(r[0]).attr("height");
                    const y_base = d3.select(r[0]).attr("y");

                    const h_shift = h_keep - h_base;
                    const y_new = y_base - h_shift;

                    d3.select(r[idx])
                        .transition()
                        .ease(d3.easeBounce)
                        .duration(500)
                        .delay(100)
                        .attr("y", function (item) { return heightStackChart - (ySingleChart(item.y0) - ySingleChart(item.y1)); })
                        .attr("height", function (item) { return ySingleChart(item.y0) - ySingleChart(item.y1); })
                        .call(yStackChart);
                }
            });
        });
    }
}

function plotData(element) {
    const entry = $(element).closest('.notebook-entry');
    const pk = entry.data('entry-pk');

    const dataScript = entry.find('script#plot-data-' + pk);
    if (!dataScript.length) return;
    const info = JSON.parse(dataScript.text());

    // remove the existing figure, if there is one
    const plotContainer = $("#plot-" + pk);
    plotContainer.find('figure').remove();
    plotContainer.append('<figure id="figure-' + pk + '"></figure>');

    const figureEl = $('#figure-' + pk);
    const width = figureEl.width() || 600;
    const data = [];
    const xlabel = entry.find('.x-axis').val() || null;
    const y1label = entry.find('.y1-axis').val();
    const y2label = entry.find('.y2-axis').val();
    const xindex = info['headers'].indexOf(xlabel);
    const y1index = info['headers'].indexOf(y1label);
    const y2index = y2label ? info['headers'].indexOf(y2label) : false;
    const xscale = 'linear';
    const interpolation = 'linear';
    const binning = 50;
    const timeformat = null;

    // check if this should be a scatter plot or a bar graph
    let barchart = true;
    if (info['data'] && info['data'][xindex]) {
        $.each(info['data'][xindex], function (i, val) {
            if (parseFloat(val)) {
                barchart = false;
            }
        });
    }

    if (barchart) {
        if (info['data'] && info['data'][xindex]) {
            $.each(info['data'][xindex], function (i, val) {
                const point = {};
                let addPoint = false;
                if (parseFloat(info['data'][y1index][i])) {
                    point[xlabel] = val;
                    point[y1label] = parseFloat(info['data'][y1index][i]);
                    addPoint = true;
                }
                if (y2label && y2index !== false && parseFloat(info['data'][y2index][i])) {
                    point[y2label] = parseFloat(info['data'][y2index][i]);
                }
                if (addPoint) {
                    data.push(point);
                }
            });
        }

        // Draw Stack Chart
        const margin = { top: 20, right: 20, bottom: 50, left: 40 };
        const x = d3.scaleBand().range([0, width]).padding(0.1);
        const y = d3.scaleLinear().range([width / 2, 0]);
        const colors = d3.scaleOrdinal(["#883A6A", "#C27844", "#551863", "#CBEFB6", "#5BC0DE"]);

        const canvas = d3.select('#figure-' + pk).append("svg").attr('id', 'plot-' + pk)
            .attr("width", width + margin.left + margin.right)
            .attr("height", width / 2 + margin.top + margin.bottom)
            .append("g")
            .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

        drawStackChart(data, xlabel, canvas, colors, x, y, width / 2);
    } else {
        if (y1label && info['data'] && info['data'][xindex] && info['data'][y1index]) {
            const x = [];
            const y = [];
            $.each(info['data'][xindex], function (i, val) {
                if (parseFloat(val) && parseFloat(info['data'][y1index][i])) {
                    x.push(parseFloat(val));
                    y.push(parseFloat(info['data'][y1index][i]));
                }
            });
            data.push({'label': y1label, 'x': x, 'y1': y});
        }
        if (y2label && y2index !== false && info['data'] && info['data'][xindex] && info['data'][y2index]) {
            const x = [];
            const y = [];
            $.each(info['data'][xindex], function (i, val) {
                if (parseFloat(val) && parseFloat(info['data'][y2index][i])) {
                    x.push(parseFloat(val));
                    y.push(parseFloat(info['data'][y2index][i]));
                }
            });
            data.push({'label': y2label, 'x': x, 'y2': y});
        }

        const xy_chart = draw_xy_chart()
            .width(width)
            .height(width / 2)
            .xlabel(xlabel)
            .y1label(y1label)
            .y2label(y2label)
            .xscale(xscale)
            .binning(binning)
            .timeformat(timeformat)
            .interpolation(interpolation)
            .scatter('scatter');
        d3.select('#figure-' + pk).append("svg").attr('id', 'plot-' + pk)
            .datum(data)
            .call(xy_chart);
    }
}

// Window-level exports for template and global access
window.initModalEntryEditors = initModalEntryEditors;
window.NotebookAnnotations = NotebookAnnotations;
window.editTags = editTags;
window.cancelTags = cancelTags;
window.submitTags = submitTags;
window.initEntries = initEntries;
window.plotData = plotData;
window.set_sketch_mode = set_sketch_mode;
window.draw_xy_chart = draw_xy_chart;
window.drawStackChart = drawStackChart;
