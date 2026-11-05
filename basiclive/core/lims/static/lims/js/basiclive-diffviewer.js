/*
 * BasicLIVE Diffraction Image Viewer Based on iviewer.js, originally from:
 * https://github.com/can3p/iviewer
 *
 * Copyright (c) 2009 - 2012 Dmitry Petrov
 * Dual licensed under the MIT and GPL licenses.
 */

(function ($) {
    "use strict";

    // Touch event to mouse event mapping (based on jquery-ui-touch-punch)
    const mouseEvents = {
        touchstart: 'mousedown',
        touchmove: 'mousemove',
        touchend: 'mouseup'
    };

    /**
     * Convert a touch event to a mouse-like event.
     * @param {jQuery.Event} event
     * @return {jQuery.Event}
     */
    function makeMouseEvent(event) {
        const touch = event.originalEvent.changedTouches[0];

        return $.extend(event, {
            type: mouseEvents[event.type],
            which: 1,
            pageX: touch.pageX,
            pageY: touch.pageY,
            screenX: touch.screenX,
            screenY: touch.screenY,
            clientX: touch.clientX,
            clientY: touch.clientY,
            isTouchEvent: true
        });
    }

    /**
     * Simple implementation of jQuery-like getters/setters.
     * @param {Function} setterFn
     * @param {Function} getterFn
     * @return {Function}
     */
    const setter = function (setterFn, getterFn) {
        return function (val) {
            if (arguments.length === 0) {
                return getterFn.apply(this);
            }
            return setterFn.apply(this, arguments);
        };
    };

    const util = {
        scaleValue: function (value, toZoom) {
            return value * toZoom / 100;
        },

        descaleValue: function (value, fromZoom) {
            return value * 100 / fromZoom;
        }
    };

    $.widget("ui.diffviewer", $.ui.mouse, {
        widgetEventPrefix: "diffviewer",
        options: {
            zoom: "fit",            // start zoom value, "fit" or scale in %
            zoom_base: 100,         // base zoom value in %
            zoom_max: 800,          // maximum zoom value in %
            zoom_min: 25,           // minimum zoom value in %
            zoom_delta: 1.4,        // zoom multiplier rate, zoom = zoom_base * zoom_delta^rate
            zoom_animation: true,   // whether the zoom should be animated
            ui_disabled: false,     // whether to disable the built-in UI controls
            update_on_resize: true, // whether to update container size on window resize
            resFunc: function (a) { // default resolution function, returns the input value
                return a;
            },
            onZoom: $.noop,         // triggered when zoom value is changed, return false to cancel zoom
            onAfterZoom: $.noop,    // triggered after image is set to the new dimensions
            onStartDrag: $.noop,    // event fired on drag begin
            onDrag: $.noop,         // event fired on drag action
            onStopDrag: $.noop,     // event fired on drag stop
            onMouseMove: $.noop,    // event fired when mouse moves over image
            onClick: $.noop,        // event fired when mouse clicks on image
            onStartLoad: null,      // event fired when image starts to load
            onFinishLoad: null      // event fired when image is loaded and initially positioned
        },

        /**
         * Initialize mouse and touch handling specifically for diffviewer without prototype pollution.
         */
        _mouseInit: function () {
            const self = this;
            this._touchActive = false;

            this.element.on('touchstart.' + this.widgetName, function (event) {
                self._touchActive = true;
                return self._mouseDown(makeMouseEvent(event));
            });

            this._mouseMoveDelegate = function (event) {
                if (self._touchActive) {
                    return self._mouseMove(makeMouseEvent(event));
                }
            };

            this._mouseUpDelegate = function (event) {
                if (self._touchActive) {
                    self._touchActive = false;
                    return self._mouseUp(makeMouseEvent(event));
                }
            };

            $(document)
                .on('touchmove.' + this.widgetName, this._mouseMoveDelegate)
                .on('touchend.' + this.widgetName, this._mouseUpDelegate);

            $.ui.mouse.prototype._mouseInit.call(this);
        },

        _mouseDestroy: function () {
            this.element.off('touchstart.' + this.widgetName);
            $(document)
                .off('touchmove.' + this.widgetName, this._mouseMoveDelegate)
                .off('touchend.' + this.widgetName, this._mouseUpDelegate);

            $.ui.mouse.prototype._mouseDestroy.call(this);
        },

        _create: function () {
            const self = this;

            // Drag state
            this.dx = 0;
            this.dy = 0;
            this.dragged = false;
            this._thumbOffset = null;
            this._posRafId = null;

            this.img_object = null;
            this.zoom_object = null;
            this.overview_object = null;
            this.overview_img = null;
            this.overview_box = null;
            this.ui_buttons = null;

            this._angle = 0;
            this.current_zoom = this.options.zoom;

            if (this.options.src === null) {
                return;
            }

            this.container = this.element;
            this._updateContainerInfo();
            this.container.css("overflow", "hidden");

            if (this.options.update_on_resize) {
                this._windowResizeHandler = function () {
                    self._updateContainerInfo();
                };
                $(window).on('resize.diffviewer', this._windowResizeHandler);
            }

            this.img_object = new $.ui.diffviewer.ImageObject(this.options.zoom_animation);

            // Bind image events
            this.img_object.object()
                .on('click', function (e) {
                    return self._click(e);
                })
                .on('wheel', function (ev) {
                    const delta = ev.originalEvent.deltaY < 0 ? 1 : -1;
                    self.zoom_by(delta);
                    return false;
                })
                .on('mousewheel', function (ev, delta) {
                    const zoom = delta > 0 ? 1 : -1;
                    self.zoom_by(zoom);
                    return false;
                })
                .prependTo(this.container);

            this._mouseMoveHandler = function (e) {
                return self.update_pos(e);
            };
            this.container.on('mousemove.diffviewer', this._mouseMoveHandler);

            this._initOverview();
            this.loadImage(this.options.src);

            if (!this.options.ui_disabled) {
                this.createui();
            }

            this._mouseInit();
        },

        _destroy: function () {
            if (this._windowResizeHandler) {
                $(window).off('resize.diffviewer', this._windowResizeHandler);
                this._windowResizeHandler = null;
            }

            if (this.container) {
                this.container.off('.diffviewer');
                this.container.removeClass("diffviewer_cursor diffviewer_drag_cursor");
            }

            $(document).off('.diffviewer_thumb');

            if (this._posRafId) {
                cancelAnimationFrame(this._posRafId);
                this._posRafId = null;
            }

            if (this.overview_object) {
                this.overview_object.remove();
                this.overview_object = null;
                this.overview_img = null;
                this.overview_box = null;
            }

            if (this.zoom_object) {
                this.zoom_object.remove();
                this.zoom_object = null;
            }

            if (this.ui_buttons) {
                this.ui_buttons.remove();
                this.ui_buttons = null;
            }

            this._mouseDestroy();
        },

        destroy: function () {
            this._destroy();
            $.Widget.prototype.destroy.call(this);
        },

        _updateContainerInfo: function () {
            const size = Math.max(this.container.height(), this.container.width());
            this.options.height = size;
            this.options.width = size;
        },

        /**
         * Initialize the overview thumbnail elements once.
         */
        _initOverview: function () {
            if (this.overview_object) {
                return;
            }
            const self = this;

            this.overview_img = $("<img>").css({
                position: "absolute",
                bottom: "0px",
                left: "0px",
                width: "128px",
                height: "128px"
            });

            this.overview_object = $("<div>")
                .addClass("diffviewer_overview_img diffviewer_common")
                .on('click', function (e) {
                    return self.thumb_click(e);
                })
                .on('mousedown', function (e) {
                    return self.thumb_drag_start(e);
                })
                .appendTo(this.container);

            this.overview_img.appendTo(this.overview_object);

            this.overview_box = $("<div>")
                .addClass("diffviewer_overview_box diffviewer_common")
                .appendTo(this.overview_object);
        },

        /**
         * Load a new image source into the viewer.
         * @param {string} src
         */
        loadImage: function (src) {
            this.img_object.object()
                .removeAttr("src")
                .removeAttr("width")
                .removeAttr("height")
                .removeAttr("style")
                .css({ position: "absolute", top: "0px", left: "0px" });

            if (!this.overview_object) {
                this._initOverview();
            } else {
                this.overview_object.hide();
            }

            this.current_zoom = this.options.zoom;
            const self = this;

            this._trigger('onStartLoad', 0, src);

            this.img_object.load(src, function () {
                self.container.addClass("diffviewer_cursor");

                if (self.options.zoom === "fit") {
                    self.fit(true);
                } else {
                    self.set_zoom(self.options.zoom, true);
                }

                if (self.options.onFinishLoad) {
                    self._trigger('onFinishLoad', 0, src);
                }
            });

            this.overview_img.attr("src", src);
        },

        /**
         * Fits image in the container.
         * @param {boolean} skip_animation
         */
        fit: function (skip_animation) {
            const origW = this.img_object.orig_width();
            const origH = this.img_object.orig_height();
            if (!origW || !origH) {
                return;
            }

            const aspectRatio = origW / origH;
            const windowRatio = this.options.width / this.options.height;
            const chooseLeft = (aspectRatio > windowRatio);
            let newZoom = 0;

            if (chooseLeft) {
                newZoom = this.options.width / origW * 100;
            } else {
                newZoom = this.options.height / origH * 100;
            }

            this.set_zoom(newZoom, skip_animation);
        },

        /**
         * Center image in container.
         */
        center: function () {
            this.setCoords(
                -Math.round((this.img_object.display_width() - this.options.width) / 2),
                -Math.round((this.img_object.display_height() - this.options.height) / 2)
            );
        },

        /**
         * Move a point in container to the center of display area.
         * @param {number} x Point in container
         * @param {number} y Point in container
         */
        moveTo: function (x, y) {
            const dx = x - Math.round(this.options.width / 2);
            const dy = y - Math.round(this.options.height / 2);

            const newX = this.img_object.x() - dx;
            const newY = this.img_object.y() - dy;

            this.setCoords(newX, newY);
        },

        /**
         * Get container offset object.
         * @return {Object}
         */
        getContainerOffset: function () {
            return $.extend({}, this.container.offset());
        },

        /**
         * Set coordinates of upper-left corner of image object.
         * @param {number} x
         * @param {number} y
         */
        setCoords: function (x, y) {
            if (!this.img_object.loaded()) {
                return;
            }

            const coords = this._correctCoords(x, y);
            this.img_object.x(coords.x);
            this.img_object.y(coords.y);

            this.setBoxCoords(x, y);
        },

        /**
         * Set coordinates of the overview box.
         * @param {number} x
         * @param {number} y
         */
        setBoxCoords: function (x, y) {
            const dispW = this.img_object.display_width();
            const dispH = this.img_object.display_height();
            if (!dispW || !dispH || !this.overview_box) {
                return;
            }

            let ox = 126 * x / dispW;
            let oy = 126 * y / dispH;
            const ow = 126 * this.options.width / dispW;
            const oh = 126 * this.options.height / dispH;

            if (ox > 0) {
                ox = 0;
            } else if (Math.abs(ox) > (126 - ow)) {
                ox = -(126 - ow);
            }

            if (oy > 0) {
                oy = 0;
            } else if (Math.abs(oy) > (126 - oh)) {
                oy = -(126 - oh);
            }

            this.overview_box.css({
                top: -oy + "px",
                left: -ox + "px",
                width: ow + "px",
                height: oh + "px"
            });
        },

        _correctCoords: function (x, y) {
            x = parseInt(x, 10);
            y = parseInt(y, 10);

            if (y > 0) {
                y = 0;
            }
            if (x > 0) {
                x = 0;
            }

            const dispW = this.img_object.display_width();
            const dispH = this.img_object.display_height();

            if (y + dispH < this.options.height) {
                y = this.options.height - dispH;
            }
            if (x + dispW < this.options.width) {
                x = this.options.width - dispW;
            }
            if (dispW <= this.options.width) {
                x = -(dispW - this.options.width) / 2;
            }
            if (dispH <= this.options.height) {
                y = -(dispH - this.options.height) / 2;
            }

            return { x: x, y: y };
        },

        /**
         * Convert coordinates on the container to coordinates on the original image.
         * @param {number} x
         * @param {number} y
         * @return {{x: number, y: number}}
         */
        containerToImage: function (x, y) {
            let coords = {
                x: x - this.img_object.x(),
                y: y - this.img_object.y()
            };

            coords = this.img_object.toOriginalCoords(coords);

            return {
                x: util.descaleValue(coords.x, this.current_zoom),
                y: util.descaleValue(coords.y, this.current_zoom)
            };
        },

        /**
         * Convert coordinates on the image to coordinates on the container.
         * @param {number} x
         * @param {number} y
         * @return {{x: number, y: number}}
         */
        imageToContainer: function (x, y) {
            const coords = {
                x: util.scaleValue(x, this.current_zoom),
                y: util.scaleValue(y, this.current_zoom)
            };

            return this.img_object.toRealCoords(coords);
        },

        /**
         * Get mouse coordinates on the image.
         * @param {jQuery.Event} e
         * @return {{x: number, y: number}}
         */
        _getMouseCoords: function (e) {
            const imgOffset = this.img_object.object().offset();
            if (!imgOffset) {
                return { x: 0, y: 0 };
            }
            const x = util.descaleValue(e.pageX - imgOffset.left, this.current_zoom);
            const y = util.descaleValue(e.pageY - imgOffset.top, this.current_zoom);

            return { x: x, y: y };
        },

        /**
         * Set image scale to new_zoom.
         * @param {number} new_zoom Image scale in %
         * @param {boolean} skip_animation
         */
        set_zoom: function (new_zoom, skip_animation) {
            if (this._trigger('onZoom', 0, new_zoom) === false) {
                return;
            }

            if (!this.img_object.loaded()) {
                return;
            }

            if (new_zoom < this.options.zoom_min) {
                new_zoom = this.options.zoom_min;
            } else if (new_zoom > this.options.zoom_max) {
                new_zoom = this.options.zoom_max;
            }

            let oldX, oldY;
            if (this.current_zoom === "fit") {
                oldX = Math.round(this.options.width / 2 + this.img_object.orig_width() / 2);
                oldY = Math.round(this.options.height / 2 + this.img_object.orig_height() / 2);
                this.current_zoom = 100;
            } else {
                oldX = -this.img_object.x() + Math.round(this.options.width / 2);
                oldY = -this.img_object.y() + Math.round(this.options.height / 2);
            }

            const newWidth = util.scaleValue(this.img_object.orig_width(), new_zoom);
            const newHeight = util.scaleValue(this.img_object.orig_height(), new_zoom);
            let newX = util.scaleValue(util.descaleValue(oldX, this.current_zoom), new_zoom);
            let newY = util.scaleValue(util.descaleValue(oldY, this.current_zoom), new_zoom);

            newX = this.options.width / 2 - newX;
            newY = this.options.height / 2 - newY;

            this.img_object.display_width(newWidth);
            this.img_object.display_height(newHeight);

            const coords = this._correctCoords(newX, newY);
            const self = this;

            this.setBoxCoords(newX, newY);
            this.img_object.setImageProps(newWidth, newHeight, coords.x, coords.y, skip_animation, function () {
                self._trigger('onAfterZoom', 0, new_zoom);
            });
            this.current_zoom = new_zoom;

            this.update_status();
        },

        /**
         * Changes zoom scale by delta.
         * Formula: zoom_base * zoom_delta^rate
         * @param {number} delta Delta number to add to current multiplier rate number
         */
        zoom_by: function (delta) {
            const closestRate = this.find_closest_zoom_rate(this.current_zoom);
            const nextRate = closestRate + delta;
            let nextZoom = this.options.zoom_base * Math.pow(this.options.zoom_delta, nextRate);

            if (delta > 0 && nextZoom < this.current_zoom) {
                nextZoom *= this.options.zoom_delta;
            }

            if (delta < 0 && nextZoom > this.current_zoom) {
                nextZoom /= this.options.zoom_delta;
            }

            this.set_zoom(nextZoom, true);
        },

        /**
         * Rotate image.
         * @param {number} deg Amount to rotate (multiples of 90).
         * @param {boolean} abs If true, absolute angle; otherwise relative.
         * @return {number|undefined} Current angle if called with no arguments.
         */
        angle: function (deg, abs) {
            if (arguments.length === 0) {
                return this.img_object.angle();
            }

            if (deg < -270 || deg > 270 || deg % 90 !== 0) {
                return;
            }

            if (!abs) {
                deg += this.img_object.angle();
            }
            if (deg < 0) {
                deg += 360;
            }
            if (deg >= 360) {
                deg -= 360;
            }

            if (deg === this.img_object.angle()) {
                return;
            }

            this.img_object.angle(deg);
            this.center();
            this._trigger('angle', 0, { angle: this.img_object.angle() });
        },

        /**
         * Finds closest multiplier rate for zoom value in O(1).
         * @param {number} value
         * @return {number}
         */
        find_closest_zoom_rate: function (value) {
            if (value === this.options.zoom_base) {
                return 0;
            }
            return Math.round(Math.log(value / this.options.zoom_base) / Math.log(this.options.zoom_delta));
        },

        /**
         * Update scale information in the container.
         */
        update_status: function () {
            const origH = this.img_object.orig_height();
            const percent = origH ? Math.round(100 * this.img_object.display_height() / origH) : 0;

            if (!this.options.ui_disabled && this.zoom_object && percent) {
                this.zoom_object.html(percent + "%");
            }

            // Show overview if zoom is at least 10% above minimum
            if (this.overview_object) {
                if (percent > this.options.zoom_min + 10) {
                    this.overview_object.show();
                } else {
                    this.overview_object.hide();
                }
            }
        },

        /**
         * Get information about the image.
         * @param {string} param Parameter name: orig_width, orig_height, display_width, display_height, angle, zoom, src
         * @param {boolean} withoutRotation
         */
        info: function (param, withoutRotation) {
            if (!param) {
                return;
            }

            switch (param) {
                case 'orig_width':
                case 'orig_height':
                    if (withoutRotation) {
                        return (this.img_object.angle() % 180 === 0
                            ? this.img_object[param]()
                            : param === 'orig_width'
                                ? this.img_object.orig_height()
                                : this.img_object.orig_width());
                    }
                    return this.img_object[param]();
                case 'display_width':
                case 'display_height':
                case 'angle':
                    return this.img_object[param]();
                case 'zoom':
                    return this.current_zoom;
                case 'src':
                    return this.img_object.object().attr('src');
            }
        },

        _mouseStart: function (e) {
            $.ui.mouse.prototype._mouseStart.call(this, e);
            if (this._trigger('onStartDrag', 0, this._getMouseCoords(e)) === false) {
                return false;
            }

            this.container.addClass("diffviewer_drag_cursor");
            this.dx = e.pageX - this.img_object.x();
            this.dy = e.pageY - this.img_object.y();
            return true;
        },

        _mouseCapture: function () {
            return true;
        },

        _handleMouseMove: function (e) {
            this._trigger('onMouseMove', e, this._getMouseCoords(e));
        },

        _mouseDrag: function (e) {
            $.ui.mouse.prototype._mouseDrag.call(this, e);
            const ltop = e.pageY - this.dy;
            const lleft = e.pageX - this.dx;

            this.setCoords(lleft, ltop);
            this._trigger('onDrag', e, this._getMouseCoords(e));
            return false;
        },
        _setOffsetCoords: function (e, offsets) {
            const x = (e.pageX - offsets.left) * this.img_object.display_width() / 128 - this.options.width / 2;
            const y = (e.pageY - offsets.top) * this.img_object.display_height() / 128 - this.options.height / 2;
            this.setCoords(-x, -y);
        },

        _mouseStop: function (e) {
            $.ui.mouse.prototype._mouseStop.call(this, e);
            this.container.removeClass("diffviewer_drag_cursor");
            this._trigger('onStopDrag', 0, this._getMouseCoords(e));
        },

        _click: function (e) {
            this._trigger('onClick', 0, this._getMouseCoords(e));
        },

        /**
         * Handle mousedown on overview thumbnail.
         * Binds mousemove and mouseup to $(document) so drag does not get stuck.
         */
        thumb_drag_start: function (e) {
            const self = this;
            this.dragged = true;
            this.container.addClass("diffviewer_drag_cursor");

            // Cache overview offset once at drag start to avoid layout thrashing during mousemove
            this._thumbOffset = this.overview_img.offset();

            $(document)
                .off('.diffviewer_thumb')
                .on('mousemove.diffviewer_thumb', function (ev) {
                    return self.thumb_drag(ev);
                })
                .on('mouseup.diffviewer_thumb', function (ev) {
                    return self.thumb_drag_end(ev);
                });

            return false;
        },

        /**
         * Handle mousemove to drag thumbnail image.
         */
        thumb_drag: function (e) {
            if (this.dragged) {
                if (this.options.onDrag) {
                    this.options.onDrag.call(this, this._getMouseCoords(e));
                }
                const offsets = this._thumbOffset || this.overview_img.offset();
                this._setOffsetCoords(e, offsets);
                return false;
            }
        },

        /**
         * Handle stop thumbnail drag.
         */
        thumb_drag_end: function () {
            this.container.removeClass("diffviewer_drag_cursor");
            this.dragged = false;
            this._thumbOffset = null;
            $(document).off('.diffviewer_thumb');
        },

        /**
         * Handle clicking within overview.
         */
        thumb_click: function (e) {
            const offsets = this.overview_img.offset();
            this._setOffsetCoords(e, offsets);
            return false;
        },

        /**
         * Update resolution reading on mousemove over image.
         * Scoped locally to avoid polluting window.x, window.y, window.z.
         * Throttled via requestAnimationFrame.
         */
        update_pos: function (e) {
            const origW = this.img_object.orig_width();
            const origH = this.img_object.orig_height();
            if (!origW || !origH) {
                return true;
            }

            const coords = this._getMouseCoords(e);
            const normX = 2.0 * Math.abs((Math.min(Math.max(coords.x, 0.0), origW) / origW) - 0.5);
            const normY = 2.0 * Math.abs((Math.min(Math.max(coords.y, 0.0), origH) / origH) - 0.5);
            const res = this.options.resFunc.call(this, Math.sqrt(normX * normX + normY * normY));
            const formatted = typeof res === 'number' ? res.toFixed(2) : res;

            if (this.zoom_object) {
                if (this._posRafId) {
                    cancelAnimationFrame(this._posRafId);
                }
                const self = this;
                this._posRafId = requestAnimationFrame(function () {
                    self.zoom_object.html(`<span>${formatted} Å</span>`);
                    self._posRafId = null;
                });
            }
            return true;
        },

        /**
         * Create zoom buttons and resolution status box.
         */
        createui: function () {
            const self = this;
            const zoomBox = $("<div>")
                .addClass("diffviewer_zoom_box diffviewer_common")
                .appendTo(this.container);

            const icons = {
                zoom_in: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" 
                    stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path stroke="none" d="M0 0h24v24H0z" fill="none" /><path d="M3 12a9 9 0 1 0 18 0a9 9 0 0 0 -18 0" />
                    <path d="M9 12h6" /><path d="M12 9v6" />
                    </svg>`,
                zoom_out: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" 
                    fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path stroke="none" d="M0 0h24v24H0z" fill="none" />
                    <path d="M3 12a9 9 0 1 0 18 0a9 9 0 1 0 -18 0" />
                    <path d="M9 12l6 0" />
                    </svg>`,
                zoom_fit: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" 
                    stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path stroke="none" d="M0 0h24v24H0z" fill="none" />
                    <path d="M4 8v-2a2 2 0 0 1 2 -2h2" /><path d="M4 16v2a2 2 0 0 0 2 2h2" />
                    <path d="M16 4h2a2 2 0 0 1 2 2v2" /><path d="M16 20h2a2 2 0 0 0 2 -2v-2" />
                    </svg>`
            };
            const makeBtn = function (btnClass, title, onClick) {
                return $("<div>", {
                    // 'class': `diffviewer_common diffviewer_button diffviewer_${btnClass}`,
                    'role': "button",
                    'tabindex': "0",
                    'aria-label': title,
                    'title': title
                })
                .on('mousedown touchstart', function (e) {
                    e.preventDefault();
                    onClick();
                    return false;
                })
                .on('keydown', function (e) {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        onClick();
                    }
                })
                .html(icons[btnClass])
                .appendTo(zoomBox);
            };

            const btnIn = makeBtn("zoom_in", "Zoom In", function () {
                self.zoom_by(1);
            });

            const btnOut = makeBtn("zoom_out", "Zoom Out", function () {
                self.zoom_by(-1);
            });

            const btnFit = makeBtn("zoom_fit", "Reset Zoom", function () {
                self.fit(true);
            });

            this.ui_buttons = btnIn.add(btnOut).add(btnFit);

            this.zoom_object = $("<div>")
                .addClass("diffviewer_zoom_status diffviewer_common")
                .appendTo(this.container);

            this.update_status();
        }
    });

    /**
     * ImageObject represents image and provides public API without extending image prototype.
     * @constructor
     * @param {boolean} do_anim
     */
    $.ui.diffviewer.ImageObject = function (do_anim) {
        this._img = $("<img>").css({
            position: "absolute",
            top: "0px",
            left: "0px"
        });

        this._loaded = false;
        this._swapDimensions = false;
        this._do_anim = do_anim || false;
        this.x(0, true);
        this.y(0, true);
        this.angle(0);
    };

    (function () {
        this._reset = function (w, h) {
            this._angle = 0;
            this._swapDimensions = false;
            this.x(0);
            this.y(0);

            this.orig_width(w);
            this.orig_height(h);
            this.display_width(w);
            this.display_height(h);
        };

        this.loaded = function () {
            return this._loaded;
        };

        this.load = function (src, loaded) {
            const self = this;
            loaded = loaded || $.noop;
            this._loaded = false;

            const img = new Image();
            img.onload = function () {
                self._loaded = true;
                self._reset(this.width, this.height);
                self._img[0].src = src;
                loaded();
            };
            img.src = src;

            this._img
                .removeAttr("src")
                .removeAttr("width")
                .removeAttr("height")
                .removeAttr("style")
                .css({ position: "absolute", top: "0px", left: "0px" });

            this.angle(0);
        };

        this._dimension = function (prefix, name) {
            const horiz = '_' + prefix + '_' + name;
            const vert = '_' + prefix + '_' + (name === 'height' ? 'width' : 'height');
            return setter(
                function (val) {
                    this[this._swapDimensions ? horiz : vert] = val;
                },
                function () {
                    return this[this._swapDimensions ? horiz : vert];
                }
            );
        };

        this.display_width = this._dimension('display', 'width');
        this.display_height = this._dimension('display', 'height');
        this.display_diff = function () {
            return Math.floor(this.display_width() - this.display_height());
        };

        this.orig_width = this._dimension('orig', 'width');
        this.orig_height = this._dimension('orig', 'height');

        this.x = setter(
            function (val, skipCss) {
                this._x = val;
                if (!skipCss) {
                    this._img.css("left", this._x + (this._swapDimensions ? this.display_diff() / 2 : 0) + "px");
                }
            },
            function () {
                return this._x;
            }
        );

        this.y = setter(
            function (val, skipCss) {
                this._y = val;
                if (!skipCss) {
                    this._img.css("top", this._y - (this._swapDimensions ? this.display_diff() / 2 : 0) + "px");
                }
            },
            function () {
                return this._y;
            }
        );

        this.angle = setter(
            function (deg) {
                const prevSwap = this._swapDimensions;

                this._angle = deg;
                this._swapDimensions = deg % 180 !== 0;

                if (prevSwap !== this._swapDimensions) {
                    const verticalMod = this._swapDimensions ? -1 : 1;
                    this.x(this.x() - verticalMod * this.display_diff() / 2, true);
                    this.y(this.y() + verticalMod * this.display_diff() / 2, true);
                }

                this._img.css('transform', 'rotate(' + deg + 'deg)');
            },
            function () {
                return this._angle;
            }
        );

        this.toOriginalCoords = function (point) {
            switch (this.angle()) {
                case 0:
                    return { x: point.x, y: point.y };
                case 90:
                    return { x: point.y, y: this.display_width() - point.x };
                case 180:
                    return { x: this.display_width() - point.x, y: this.display_height() - point.y };
                case 270:
                    return { x: this.display_height() - point.y, y: point.x };
            }
        };

        this.toRealCoords = function (point) {
            switch (this.angle()) {
                case 0:
                    return { x: this.x() + point.x, y: this.y() + point.y };
                case 90:
                    return { x: this.x() + this.display_width() - point.y, y: this.y() + point.x };
                case 180:
                    return { x: this.x() + this.display_width() - point.x, y: this.y() + this.display_height() - point.y };
                case 270:
                    return { x: this.x() + point.y, y: this.y() + this.display_height() - point.x };
            }
        };

        this.object = function () {
            return this._img;
        };

        this.setImageProps = function (disp_w, disp_h, x, y, skip_animation, complete) {
            complete = complete || $.noop;

            this.display_width(disp_w);
            this.display_height(disp_h);
            this.x(x, true);
            this.y(y, true);

            const w = this._swapDimensions ? disp_h : disp_w;
            const h = this._swapDimensions ? disp_w : disp_h;

            const params = {
                width: w,
                height: h,
                top: y - (this._swapDimensions ? this.display_diff() / 2 : 0) + "px",
                left: x + (this._swapDimensions ? this.display_diff() / 2 : 0) + "px"
            };

            if (this._do_anim && !skip_animation) {
                this._img.animate(params, {
                    duration: 200,
                    complete: complete
                });
            } else {
                this._img.css(params);
                setTimeout(complete, 0);
            }
        };
    }).apply($.ui.diffviewer.ImageObject.prototype);

})(jQuery);
