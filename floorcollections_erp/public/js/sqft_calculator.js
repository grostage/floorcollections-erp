frappe.ui.form.on("Quotation", {
    refresh(frm) {
        add_sqft_calculator_button(frm);
    },
});

frappe.ui.form.on("Sales Order", {
    refresh(frm) {
        add_sqft_calculator_button(frm);
    },
});


function add_sqft_calculator_button(frm) {
    frm.add_custom_button(
        __("SQFT Calculator"),
        () => open_sqft_calculator(frm),
        __("Tools")
    );
}


function open_sqft_calculator(frm) {

    const dialog = new frappe.ui.Dialog({
        title: __("SQFT Calculator"),
        size: "large",

        fields: [

            // =========================
            // LEFT COLUMN
            // =========================

            {
                fieldname: "required_sqft",
                label: __("Required Sqft"),
                fieldtype: "Float",
                reqd: 1,
            },

            {
                fieldname: "size",
                label: __("Tile Size"),
                fieldtype: "Autocomplete",
                reqd: 1,
                description: __("Type to search, for example: 600 X 1200"),
            },

            {
                fieldname: "pieces_per_box",
                label: __("Pieces Per Box"),
                fieldtype: "Int",
                default: 1,
                reqd: 1,
            },

            {
                fieldname: "wastage_percent",
                label: __("Wastage %"),
                fieldtype: "Float",
                default: 0,
            },

            // =========================
            // RIGHT COLUMN
            // =========================

            {
                fieldtype: "Column Break",
                fieldname: "input_column_break",
            },

            {
                fieldname: "sell_by",
                label: __("Sell By"),
                fieldtype: "Select",
                options: ["Box", "Piece"],
                default: "Box",
                reqd: 1,
            },

            {
                fieldname: "selected_width",
                label: __("Width (mm)"),
                fieldtype: "Float",
                read_only: 1,
            },

            {
                fieldname: "selected_height",
                label: __("Height (mm)"),
                fieldtype: "Float",
                read_only: 1,
            },

            {
                fieldname: "required_with_wastage",
                label: __("Area incl. Wastage"),
                fieldtype: "Float",
                read_only: 1,
            },


            // =========================
            // RESULT SECTION
            // =========================

            {
                fieldtype: "Section Break",
                fieldname: "results_section",
                label: __("Calculation Result"),
            },

            // LEFT RESULT COLUMN

            {
                fieldname: "sqft_per_piece",
                label: __("Sqft / Piece"),
                fieldtype: "Float",
                precision: 4,
                read_only: 1,
            },

            {
                fieldname: "boxes_required",
                label: __("Boxes Required"),
                fieldtype: "Int",
                read_only: 1,
            },

            {
                fieldname: "actual_coverage",
                label: __("Actual Coverage Sqft"),
                fieldtype: "Float",
                read_only: 1,
            },

            // RIGHT RESULT COLUMN

            {
                fieldtype: "Column Break",
                fieldname: "result_column_break",
            },

            {
                fieldname: "sqft_per_box",
                label: __("Sqft / Box"),
                fieldtype: "Float",
                precision: 4,
                read_only: 1,
            },

            {
                fieldname: "pieces_required",
                label: __("Pieces Required"),
                fieldtype: "Int",
                read_only: 1,
            },

            {
                fieldname: "extra_coverage",
                label: __("Extra Coverage Sqft"),
                fieldtype: "Float",
                read_only: 1,
            },
        ],

        primary_action_label: __("Calculate"),

        primary_action(values) {

            const selected_size =
                dialog._size_map?.[values.size];

            if (!selected_size) {
                frappe.msgprint(
                    __("Please select a valid size from the search results.")
                );
                return;
            }

            frappe.call({
                method:
                    "floorcollections_erp.sqft_calculator.api.calculate",

                args: {
                    required_sqft: values.required_sqft,
                    width: selected_size.width,
                    height: selected_size.height,
                    pieces_per_box: values.pieces_per_box,
                    wastage_percent: values.wastage_percent,
                    sell_by: values.sell_by,
                },

                freeze: true,
                freeze_message: __("Calculating..."),

                callback(r) {

                    if (!r.message) {
                        return;
                    }

                    const result = r.message;

                    dialog.set_value(
                        "selected_width",
                        result.width
                    );

                    dialog.set_value(
                        "selected_height",
                        result.height
                    );

                    dialog.set_value(
                        "required_with_wastage",
                        result.required_with_wastage
                    );

                    dialog.set_value(
                        "sqft_per_piece",
                        result.sqft_per_piece
                    );

                    dialog.set_value(
                        "sqft_per_box",
                        result.sqft_per_box
                    );

                    dialog.set_value(
                        "boxes_required",
                        result.boxes_required
                    );

                    dialog.set_value(
                        "pieces_required",
                        result.pieces_required
                    );

                    dialog.set_value(
                        "actual_coverage",
                        result.actual_coverage
                    );

                    dialog.set_value(
                        "extra_coverage",
                        result.extra_coverage
                    );
                },
            });
        },
    });


    dialog._size_map = {};


    // -------------------------------------
    // SIZE SEARCH
    // -------------------------------------

    function load_sizes(search_text = "") {

        frappe.call({
            method:
                "floorcollections_erp.sqft_calculator.api.search_sizes",

            args: {
                txt: search_text,
            },

            callback(r) {

                const rows = r.message || [];

                const options = [];

                rows.forEach((row) => {

                    dialog._size_map[row.label] = row;

                    options.push(row.label);
                });

                const size_control =
                    dialog.fields_dict.size;

                if (
                    size_control &&
                    typeof size_control.set_data === "function"
                ) {
                    size_control.set_data(options);
                }
            },
        });
    }


    // Load initial sizes
    load_sizes("");


    const size_input =
        dialog.fields_dict.size.$input;


    size_input.on(
        "input",
        frappe.utils.debounce(function () {

            const text =
                ($(this).val() || "").trim();

            load_sizes(text);

        }, 250)
    );


    // When a predefined size is selected,
    // immediately show width and height.

    size_input.on("change", function () {

        const selected =
            dialog._size_map[$(this).val()];

        if (selected) {

            dialog.set_value(
                "selected_width",
                selected.width
            );

            dialog.set_value(
                "selected_height",
                selected.height
            );
        }
    });


    dialog.show();
}
