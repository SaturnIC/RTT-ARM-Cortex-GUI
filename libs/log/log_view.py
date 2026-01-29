import time
import tkinter as tk
import FreeSimpleGUI as sg

# Constants
FILTER_APPLICATION_WAIT_TIME_s = 1
COLOR_BLUE = 'blue'
COLOR_HIGHLIGHT = 'LightGreen'
COLOR_BLACK = 'black'
COLOR_LIGHT_GREY = "LightGray"

class LogView:
    def __init__(self, log_widget, filter_widget, highlight_widget, pause_button, window):
        self.window = window
        # store widgets
        self.log_widget = log_widget
        self.filter_input_widget = filter_widget
        self.highlight_input_widget = highlight_widget
        self.pause_button_widget = pause_button
        # store default colors
        self.default_background_color = sg.theme_input_background_color()
        self.default_text_color = sg.theme_input_text_color()
        # input fields
        self.last_filter_change_time = 0
        self.last_highlight_change_time = 0
        self.last_mcu_change_time = 0
        self.last_filter_input = ""
        self.last_highlight_input = ""
        self.last_mcu_input = ""
        self.active_highlight_string = ""
        self.active_filter_string = ""
        self.active_mcu_string = ""
        self.filter_input_active = False
        self.highlight_input_active = False
        self.mcu_input_active = False
        # configure tags
        self.log_widget.Widget.tag_config("highlight", foreground="LightGreen")
        # log state
        self.current_line_no = 1

    def clear_log(self):
        self.update_log("", append=False)
        self.current_line_no = 1
        self.log_widget.Widget.tag_config("highlight", foreground="LightGreen")

    def insert_highlighted_text(self, highlighted_text_list):
        if not highlighted_text_list:
            return

        # Get start position before insertion
        start_index = "0.0" #self.log_widget.Widget.index(tk.END)

        # Build single string and tag ranges
        full_text = ""
        tag_ranges = []
        for text, highlighted in highlighted_text_list:
            line_text = text + '\n'
            full_text += line_text
            if highlighted:
                start = f"{self.current_line_no}.0"
                end = f"{self.current_line_no}.0 lineend" #f"{start}+{len(text)}c"
                tag_ranges.append((start, end))
            self.current_line_no += 1

        # Bulk insert and apply tags
        self.log_widget.Widget.insert(tk.END, full_text)
        for start, end in tag_ranges:
            self.log_widget.Widget.tag_add("highlight", start, end)

        # Scroll only once
        self.log_widget.Widget.see(tk.END)

    def update_log(self, text, append):
        self.log_widget.update(text, append=append)

    def set_highlight_color_for_input_widget(self, gui_element_label):
        self.window[gui_element_label].update(background_color=COLOR_HIGHLIGHT)
        self.window[gui_element_label].update(text_color=COLOR_BLACK)

    def set_default_color_for_input_widget(self, gui_element_label):
        self.window[gui_element_label].update(background_color=self.default_background_color)
        self.window[gui_element_label].update(text_color=self.default_text_color)

    def handle_coloring_of_input_widget(self, input_active, input_label):
        if input_active:
            self.set_highlight_color_for_input_widget(input_label)
        else:
            self.set_default_color_for_input_widget(input_label)
    
    def handle_widget_highlighting(self, filter_input, highlight_input, mcu_input):
        retVal = {}
        current_time = time.time()

        # handle change of inputs
        ## filter input
        if self.last_filter_input != filter_input:
            self.last_filter_input = filter_input
            self.last_filter_change_time = current_time
            self.filter_input_active = True
            self.handle_coloring_of_input_widget(True, "-FILTER-")
        ## highlight input
        if self.last_highlight_input != highlight_input:
            self.last_highlight_input = highlight_input
            self.last_highlight_change_time = current_time
            self.highlight_input_active = True
            self.handle_coloring_of_input_widget(True, "-HIGHLIGHT-")
        ## mcu input
        if self.last_mcu_input != mcu_input:
            self.last_mcu_input = mcu_input
            self.last_mcu_change_time = current_time
            self.mcu_input_active = True
            self.handle_coloring_of_input_widget(True, "-MCU-")

        # Handle application of changed input stings
        ## highlight input widget
        if (current_time - self.last_filter_change_time > FILTER_APPLICATION_WAIT_TIME_s) \
           and (self.filter_input_active == True):
            if (self.active_filter_string != self.last_filter_input):
                # change timer expired for new filter string
                self.active_filter_string = self.last_filter_input
                retVal["filter_string"] = self.active_filter_string
            # disable highlighting
            self.handle_coloring_of_input_widget(False, "-FILTER-")
            self.filter_input_active = False
        ## highlight input widget
        if (current_time - self.last_highlight_change_time > FILTER_APPLICATION_WAIT_TIME_s) \
           and (self.highlight_input_active == True):
            if (self.active_highlight_string != self.last_highlight_input):
                # change timer expired for new highlight string
                self.active_highlight_string = self.last_highlight_input
                retVal["highlight_string"] = self.active_highlight_string
            # disable highlighting
            self.handle_coloring_of_input_widget(False, "-HIGHLIGHT-")
            self.highlight_input_active = False
        ## highlight mcu widget
        if (current_time - self.last_mcu_change_time > FILTER_APPLICATION_WAIT_TIME_s) \
           and (self.mcu_input_active == True):
            if (self.active_mcu_string != self.last_mcu_input):
                # change timer expired for new mcu string
                self.active_mcu_string = self.last_mcu_input
                retVal["mcu_string"] = self.active_mcu_string
            # disable highlighting
            self.handle_coloring_of_input_widget(False, "-MCU-")
            self.mcu_input_active = False

        return retVal

    def display_log_update(self, update_info):
        """
        Display the processed log update
        """
        # parse input dict
        highlighted_text_list = update_info['highlighted_text_list']
        append = update_info['append']

        # Reset log
        if append == False:
            self.clear_log()

        # Inset log lines in log widget
        self.insert_highlighted_text(highlighted_text_list)