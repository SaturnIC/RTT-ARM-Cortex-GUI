import FreeSimpleGUI as sg
import json
import os
import time
import queue
import threading
import argparse
import matplotlib
matplotlib.rcParams['font.family'] = 'sans-serif'
matplotlib.rcParams['font.sans-serif'] = ['Inter', 'Segoe UI', 'Helvetica Neue', 'DejaVu Sans']
matplotlib.rcParams['mathtext.default'] = 'regular'

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import libs.log.log_controller as log_controller
from datetime import datetime
from libs.jlink.rtt_handler import RTTHandler
from libs.jlink.demo_rtt_handler import DemoRTTHandler
from libs.jlink.rtt_handler_interface import RTTHandlerInterface
from libs.log.log_view import LogView
from platformdirs import user_data_dir
from pathlib import Path
import fnmatch
import re

# constants
LOG_UPDATE_TIME_INTERVAL_ms = 100

# configure config file path
APP_NAME = "RTT_GUI"
APP_AUTHOR = "SaturnIC"
CONFIG_FILE_NAME = "config.json"
config_file_dir = Path(user_data_dir(APP_NAME, APP_AUTHOR))
config_file_dir.mkdir(parents=True, exist_ok=True)

class RTTViewer:
    def __init__(self, demo=False):
        self.filter_input_string = ""
        self.highlight_input_string = ""
        self.last_processed_time = time.time()
        self.log_update_time_interval_s = LOG_UPDATE_TIME_INTERVAL_ms / 1000.0

        # Create queues
        self.log_processing_input_queue = queue.Queue()
        self.display_output_queue = queue.Queue()

        # Initialize RTT Handler
        if demo:
            self._rtt_handler = DemoRTTHandler(self.log_processing_input_queue)
        else:
            self._rtt_handler = RTTHandler(self.log_processing_input_queue)
        self.supported_mcu_list = self._rtt_handler.get_supported_mcus()
        # Load configuration
        self._config_file_path = os.path.join(config_file_dir, CONFIG_FILE_NAME)
        config = self._load_config()
        self.mcu_history = config.get('mcu_history', [])
        self.last_interface = config.get('last_interface', 'SWD')
        self.data_series = config.get('data_series', [])
        # Initialize MCU combo values with history
        # GUI setup
        # Modern dark color palette
        BG = '#1E1E1E'
        SURFACE = '#2D2D2D'
        TEXT = '#E0E0E0'
        MUTED = '#909090'
        SETTINGS = '#D4A574'
        BTN_TEXT = '#DCDCDC'
        SERIES = '#4EA88A'
        LABEL = '#B8B8B8'
        ACCENT = '#2D6A9F'
        SUCCESS = '#5FA05F'
        DANGER = '#C05050'
        INPUT_BG = '#3C3C3C'
        BORDER = '#404040'

        sg.theme('DarkGray13')
        sg.theme_background_color(BG)
        sg.theme_element_background_color(BG)
        sg.theme_text_color(TEXT)
        sg.theme_text_element_background_color(BG)
        sg.theme_input_background_color(INPUT_BG)
        sg.theme_input_text_color(TEXT)
        sg.theme_button_color((BTN_TEXT, SURFACE))
        sg.theme_element_text_color(LABEL)

        FONT = ('Segoe UI', 10, 'bold')
        FONT_BOLD = ('Segoe UI', 10, 'bold')
        FONT_MONO = ('Consolas', 10)
        FONT_MONO_SM = ('Consolas', 9)

        log_tab = [
            [sg.Multiline(size=(80, 20), key='-LOG-', expand_x=True, expand_y=True, font=FONT_MONO)],
            [sg.Text('Filter:', font=FONT, text_color=SERIES), sg.Input(key='-FILTER-', size=(18, 1), enable_events=True, font=FONT),
             sg.Text('Highlight:', font=FONT, text_color=SERIES), sg.Input(key='-HIGHLIGHT-', size=(18, 1), enable_events=True, font=FONT),
             sg.Push(),
             sg.Button('Pause', key='-PAUSE-', font=FONT, button_color=(SERIES, SURFACE)),
             sg.Button('Clear', key='-CLEAR-', font=FONT, button_color=(SERIES, SURFACE)),
             sg.Button('Save', key='-SAVE-', font=FONT, button_color=(SERIES, SURFACE))]
        ]

        data_series_tab = [[sg.Column([
            [sg.Text('Series Configuration', font=FONT_BOLD, text_color=SERIES)],
            [sg.HorizontalSeparator()],
            [sg.Text('Name', font=FONT, text_color=LABEL, size=(8, 1)),
             sg.Input(key='-SERIES_NAME-', size=(25, 1), font=FONT)],
            [sg.Text('Pattern', font=FONT, text_color=LABEL, size=(8, 1)),
             sg.Input(key='-SERIES_PATTERN-', size=(40, 1), font=FONT)],
            [sg.Button('Add', key='-ADD_SERIES-', font=FONT, button_color=(BTN_TEXT, SURFACE)),
             sg.Button('Update', key='-UPDATE_SERIES-', font=FONT, button_color=(BTN_TEXT, SURFACE)),
             sg.Button('Remove', key='-REMOVE_SERIES-', font=FONT, button_color=(DANGER, SURFACE))],
            [sg.HorizontalSeparator()],
            [sg.Column([
                [sg.Text('Defined Series', font=FONT_BOLD, text_color=SERIES)],
                [sg.Listbox(values=[f"{s['name']}: {s['pattern']}" for s in self.data_series],
                            key='-SERIES_LIST-', size=(40, 8), font=FONT_MONO_SM,
                            select_mode=sg.LISTBOX_SELECT_MODE_SINGLE, enable_events=True)]
            ], vertical_alignment='top'),
             sg.Column([
                [sg.Text(' ', font=FONT)],
                [sg.Button('Activate \u25B6', key='-ACTIVATE_SERIES-', font=FONT, button_color=(SUCCESS, SURFACE), size=(10, 1))],
                [sg.Button('\u25C4 Deactivate', key='-DEACTIVATE_SERIES-', font=FONT, button_color=(DANGER, SURFACE), size=(10, 1))],
            ], vertical_alignment='center', element_justification='center'),
             sg.Column([
                [sg.Text('Active', font=FONT_BOLD, text_color=SERIES)],
                [sg.Listbox(values=[s['name'] for s in self.data_series],
                            key='-ACTIVE_SERIES-', size=(25, 8), font=FONT_MONO_SM,
                            select_mode=sg.LISTBOX_SELECT_MODE_EXTENDED, enable_events=True)]
            ], vertical_alignment='top')],
            [sg.HorizontalSeparator()],
            [sg.Text('Recorded Values', font=FONT_BOLD, text_color=SERIES),
             sg.Push(),
             sg.Button('Clear Data', key='-CLEAR_DATA-', font=FONT, button_color=(DANGER, SURFACE))],
            [sg.Multiline(size=(70, 10), key='-SERIES_VALUES-', expand_x=True, font=FONT_MONO_SM, disabled=True)]
        ], expand_x=True, expand_y=True, pad=(0, (4, 0)))]]

        plot_tab = [[sg.Column([
            [sg.Text('Series 1:', font=FONT, text_color=SERIES), sg.Combo(['—'], default_value='—', key='-PLOT_SERIES_1-', size=(20, 1), enable_events=True, readonly=True, font=FONT),
             sg.Text('Series 2:', font=FONT, text_color=SERIES), sg.Combo(['—'], default_value='—', key='-PLOT_SERIES_2-', size=(20, 1), enable_events=True, readonly=True, font=FONT),
             sg.Text('Series 3:', font=FONT, text_color=SERIES), sg.Combo(['—'], default_value='—', key='-PLOT_SERIES_3-', size=(20, 1), enable_events=True, readonly=True, font=FONT)],
            [sg.Canvas(key='-CANVAS-', size=(800, 600), expand_x=True, expand_y=True)]
        ], expand_x=True, expand_y=True, pad=(0, (4, 0)))]]

        self._layout = [
            [sg.Text('MCU:', font=FONT, text_color=SETTINGS),
             sg.Combo(self._build_mcu_combo_values(),
                      default_value='DEMO_MCU' if demo else 'STM32F427II',
                      key='-MCU-', size=(20, 1), enable_events=True, auto_size_text=False, font=FONT),
             sg.Text('Interface:', font=FONT, text_color=SETTINGS, pad=((15, 0), (0, 0))),
             sg.Combo(['SWD', 'JTAG'], default_value=self.last_interface,
                      key='-INTERFACE-', size=(8, 1), auto_size_text=False, font=FONT),
             sg.Push(),
             sg.Button('Connect', key='-CONNECT-', font=FONT_BOLD, button_color=('#FFFFFF', '#2D6A9F'), pad=((5, 5), (0, 0))),
             sg.Button('Disconnect', key='-DISCONNECT-', disabled=True, font=FONT, button_color=('#DCDCDC', '#3A2020'), pad=((0, 10), (0, 0))),
             sg.Text('\u25CF', key='-STATUS_DOT-', font=('Segoe UI', 12), text_color='#909090', pad=(0, 0))],
            [sg.HorizontalSeparator()],
            [sg.TabGroup([
                [sg.Tab('Log', log_tab, key='-LOG_TAB-'),
                 sg.Tab('Data Series', data_series_tab, key='-DATA_SERIES_TAB-'),
                 sg.Tab('Plot', plot_tab, key='-PLOT_TAB-')]
            ], expand_x=True, expand_y=True, font=FONT_BOLD,
               title_color='#788898', selected_title_color='#4A90D9',
               selected_background_color=SURFACE)]
        ]

        self._window = sg.Window('ARM Cortex RTT GUI', self._layout, finalize=True, resizable=True)

        # Set initial MCU selection to the most recently used MCU if available
        if demo:
            self._window['-MCU-'].update(value='DEMO_MCU')
        elif self.mcu_history:
            self._window['-MCU-'].update(value=self.mcu_history[0])
        else:
            self._window['-MCU-'].update(value='STM32F427II')

        # Set minimum size
        self._window.set_min_size((800, 600))

        # Initialize GUI state
        self._update_gui_status(False)

        self.mcu_filter_string = ''
        self.last_mcu_filter_string = ""
        self.mcu_list_last_update_time = time.time()

        # Bind the <KeyRelease> event to the Combo widget
        self._window['-MCU-'].Widget.bind("<KeyPress>", lambda event: self._window.write_event_value('-MCU-KEYRELEASE-', event))

        # Create LogView instance
        self.log_view = LogView(
            log_widget=self._window['-LOG-'],
            filter_widget=self._window['-FILTER-'],
            highlight_widget=self._window['-HIGHLIGHT-'],
            pause_button=self._window['-PAUSE-'],
            window=self._window
        )

        # Create log handler
        self.log_handler = log_controller.create_log_processor_and_displayer(self.log_view)

        # Plot data
        self.selected_plot_series = ["", "", ""]
        self.active_series_names = [s['name'] for s in self.data_series]
        self.series_data = {}  # Dictionary to store recorded values for each series
        self.selected_series_for_view = ""  # Currently selected series for viewing values
        self._last_series_values_content = ""
        self._last_plot_data_lengths = {}
        self.plot_fig = None
        self.plot_ax = None
        self.plot_canvas_agg = None
        self.plot_lines = {}
        self.plot_toolbar = None

        # Populate series UI with loaded data
        self._update_series_ui()

        # Initialize plot
        self._update_plot()

        self.demo = demo

    def _update_gui_status(self, connected):
        if connected:
            self._window['-STATUS_DOT-'].update(text_color='#5FA05F')
            self._window['-DISCONNECT-'].update(disabled=False, button_color=('#DCDCDC', '#802020'))
        else:
            self._window['-STATUS_DOT-'].update(text_color='#909090')
            self._window['-DISCONNECT-'].update(disabled=True, button_color=('#DCDCDC', '#3A2020'))
        self._window['-CONNECT-'].update(disabled=connected)
        #self._window['-PAUSE-'].update(disabled=not connected)

    def _log_processing_thread(self):
        while True:
            try:
                # Get element from input queue
                log_input = self.log_processing_input_queue.get(timeout=0.1)

                # Parse log processing item
                line = log_input["line"] if "line" in log_input else ""
                filter_string = log_input["filter_string"] if "filter_string" in log_input else None
                highlight_string = log_input["highlight_string"] if "highlight_string" in log_input else None
                pause_string = log_input["pause_string"] if "pause_string" in log_input else None

                # Extract plot data
                if line and self.active_series_names:
                    self._extract_plot_data(line)

                # Invoke processing
                update_info = self.log_handler["process"](line, filter_string, highlight_string, pause_string)

                # Add processing result to output queue
                self.display_output_queue.put(update_info)
            except queue.Empty:
                pass
            time.sleep(0.01)

    def _process_display_output_queue(self):
        count = 0
        max_per_call = 20  # Limit to 100 lines per GUI update to prevent overload
        highlighted_log_lines = []
        update_info = []
        while not self.display_output_queue.empty() and count < max_per_call:
            try:
                update_info = self.display_output_queue.get_nowait()
                highlighted_log_lines += update_info['highlighted_text_list']
                count += 1
                if update_info["append"] == False:
                    break
            except queue.Empty:
                break
        if update_info != []:
            # print processed lines
            #highlighted_log_lines.append((f"count on print: {count}", False))
            update_info['highlighted_text_list'] = highlighted_log_lines
            self.log_view.display_log_update(update_info)
        #else:
        #    # call log gui update at least once per second
        #    if (datetime.now() - log_controller.get_last_log_gui_filter_update_date()).total_seconds() > log_controller.GUI_MINIMUM_REFRESH_INTERVAL_s:
        #        update_info = self.log_handler["process"]("")
        #        self.log_view.display_log_update(update_info)

    def _filter_mcu_list(self, filter_string):
        input_text = filter_string.upper()
        filtered = [mcu for mcu in self.supported_mcu_list if input_text in mcu]
        self._window['-MCU-'].update(values=filtered)

    def _load_config(self):
        try:
            with open(self._config_file_path, 'r') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {'mcu_history': [], 'last_interface': 'SWD'}

    def _save_config(self):
        try:
            config = {
                'mcu_history': self.mcu_history,
                'last_interface': self.last_interface,
                'data_series': self.data_series
            }
            with open(self._config_file_path, 'w') as f:
                json.dump(config, f)
        except Exception:
            pass

    def _build_mcu_combo_values(self):
        combo = []
        if self.mcu_history:
            combo.append('--- Last used ---')
            combo.extend(self.mcu_history)
        combo.append('--- All ---')
        combo.extend(self.supported_mcu_list)
        return combo

    def _update_mcu_combo(self):
        selected_mcu = self._window['-MCU-'].get()
        self._window['-MCU-'].update(values=self._build_mcu_combo_values())
        self._window['-MCU-'].update(value=selected_mcu)

    def _update_mcu_history(self, mcu):
        if mcu in self.supported_mcu_list:
            if mcu in self.mcu_history:
                pass
                #self.mcu_history.remove(mcu)
            else:
                self.mcu_history.insert(0, mcu)
            self.mcu_history = self.mcu_history[:10]
            self._save_config()
            self._update_mcu_combo()

    def _extract_plot_data(self, line):
        # Extract data for all active series
        line = line.rstrip('\n\r')
        for series_name in self.active_series_names:
            series = next((s for s in self.data_series if s['name'] == series_name), None)
            if not series:
                continue

            pattern = series['pattern']
            glob_pattern = pattern.replace('<N>', '*')
            if fnmatch.fnmatch(line, glob_pattern):
                # Build regex: <N> = capture group, * = non-capturing wildcard
                regex_parts = []
                j = 0
                while j < len(pattern):
                    if pattern[j:j+3] == '<N>':
                        regex_parts.append(r'(\d+(?:\.\d+)?)')
                        j += 3
                    elif pattern[j] == '*':
                        regex_parts.append('.*?')
                        j += 1
                    else:
                        regex_parts.append(re.escape(pattern[j]))
                        j += 1
                regex_pattern = ''.join(regex_parts)
                match = re.search(regex_pattern, line)
                if match:
                    timestamp = time.time()
                    if series_name not in self.series_data:
                        self.series_data[series_name] = []

                    for i in range(1, match.lastindex + 1):
                        try:
                            value = float(match.group(i))
                            self.series_data[series_name].append((timestamp, value, i))
                        except (ValueError, IndexError):
                            pass

    # Modern dark dashboard color palette (matches UI theme)
    COLORS = ['#5B9FD4', '#C05050', '#5FA05F', '#C0A040', '#40A0A0', '#9070B0', '#C07040']
    BG_COLOR = '#1E1E1E'
    SURFACE_COLOR = '#2D2D2D'
    TEXT_COLOR = '#909090'
    TEXT_BOLD = '#E0E0E0'
    GRID_COLOR = '#404040'
    SPINE_COLOR = '#404040'

    def _init_plot(self, canvas):
        import tkinter as tk

        for item in canvas.winfo_children():
            item.destroy()

        fig = plt.Figure(figsize=(6, 4), facecolor=self.BG_COLOR, dpi=100)
        ax = fig.add_subplot(111, facecolor=self.SURFACE_COLOR)

        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        for spine in ['bottom', 'left']:
            ax.spines[spine].set_color(self.SPINE_COLOR)
            ax.spines[spine].set_linewidth(0.8)

        ax.tick_params(axis='both', colors=self.TEXT_COLOR, labelsize=9, length=4, width=0.8)
        ax.grid(True, color=self.GRID_COLOR, linewidth=0.5, alpha=0.6, linestyle='-')
        ax.set_axisbelow(True)

        canvas_agg = FigureCanvasTkAgg(fig, master=canvas)
        canvas_agg.get_tk_widget().pack(fill='both', expand=True)

        toolbar = NavigationToolbar2Tk(canvas_agg, canvas)
        toolbar.pack_forget()

        btn_frame = tk.Frame(canvas, bg=self.BG_COLOR)
        btn_frame.pack(fill='x', side='bottom')

        btn_style = {
            'font': ('Segoe UI', 10),
            'bg': '#2D2D2D',
            'fg': '#B0B0B0',
            'activebackground': '#404040',
            'activeforeground': '#E0E0E0',
            'relief': 'flat',
            'padx': 8,
            'pady': 2,
            'bd': 0,
        }

        def make_btn(parent, text, cmd):
            b = tk.Button(parent, text=text, command=cmd, **btn_style)
            b.pack(side='left', padx=1, pady=2)
            return b

        make_btn(btn_frame, 'Home', toolbar.home)
        make_btn(btn_frame, '\u25C0', toolbar.back)
        make_btn(btn_frame, '\u25B6', toolbar.forward)
        make_btn(btn_frame, 'Pan', toolbar.pan)
        make_btn(btn_frame, 'Zoom', toolbar.zoom)
        make_btn(btn_frame, '\u2B07', toolbar.save_figure)

        canvas.bind('<Configure>', self._on_canvas_resize)

        return fig, ax, canvas_agg, toolbar

    def _smooth_data(self, times, values, n_points=500):
        if len(times) < 4:
            return np.array(times), np.array(values)
        t = np.array(times)
        v = np.array(values)
        t_smooth = np.linspace(t[0], t[-1], n_points)
        v_smooth = np.interp(t_smooth, t, v)
        return t_smooth, v_smooth

    def _update_plot(self):
        canvas_elem = self._window['-CANVAS-']
        canvas = canvas_elem.TKCanvas

        if self.plot_fig is None:
            self.plot_fig, self.plot_ax, self.plot_canvas_agg, self.plot_toolbar = self._init_plot(canvas)

        self.plot_ax.clear()
        self.plot_lines = {}
        has_data = False

        self.plot_ax.spines['top'].set_visible(False)
        self.plot_ax.spines['right'].set_visible(False)
        for spine in ['bottom', 'left']:
            self.plot_ax.spines[spine].set_color(self.SPINE_COLOR)
            self.plot_ax.spines[spine].set_linewidth(0.8)
        self.plot_ax.tick_params(axis='both', colors=self.TEXT_COLOR, labelsize=9, length=4, width=0.8)
        self.plot_ax.grid(True, color=self.GRID_COLOR, linewidth=0.5, alpha=0.6, linestyle='-')
        self.plot_ax.set_axisbelow(True)

        plot_series = [s for s in self.selected_plot_series if s]
        all_values = []
        global_start_time = None
        for series_name in plot_series:
            if series_name in self.series_data and self.series_data[series_name]:
                t0 = self.series_data[series_name][0][0]
                if global_start_time is None or t0 < global_start_time:
                    global_start_time = t0

        for i, series_name in enumerate(plot_series):
            if series_name in self.series_data and self.series_data[series_name]:
                has_data = True
                data = self.series_data[series_name]
                values = [d[1] for d in data]
                times = [d[0] - global_start_time for d in data]
                all_values.extend(values)
                color = self.COLORS[i % len(self.COLORS)]

                t_smooth, v_smooth = self._smooth_data(times, values)

                self.plot_ax.plot(
                    t_smooth, v_smooth, color=color, linewidth=4,
                    alpha=0.25, solid_capstyle='round'
                )

                line, = self.plot_ax.plot(
                    t_smooth, v_smooth, label=series_name, color=color,
                    linewidth=2, solid_capstyle='round', antialiased=True
                )
                self.plot_lines[series_name] = line

        if has_data and all_values:
            y_min = min(all_values)
            y_max = max(all_values)
            y_range = y_max - y_min
            if y_range < 1e-10:
                y_range = max(abs(y_max) * 0.1, 1.0)
            y_margin = y_range * 0.05
            self.plot_ax.set_ylim(y_min - y_margin, y_max + y_margin)

            for i, series_name in enumerate(plot_series):
                if series_name in self.series_data and self.series_data[series_name]:
                    data = self.series_data[series_name]
                    values = [d[1] for d in data]
                    times = [d[0] - global_start_time for d in data]
                    color = self.COLORS[i % len(self.COLORS)]
                    t_smooth, v_smooth = self._smooth_data(times, values)
                    self.plot_ax.fill_between(
                        t_smooth, v_smooth, y_min - y_margin,
                        alpha=0.08, color=color, linewidth=0
                    )

        if has_data:
            self.plot_ax.set_xlabel('Time  (s)', color=self.TEXT_COLOR, fontsize=10, labelpad=8)
            self.plot_ax.set_ylabel('Value', color=self.TEXT_COLOR, fontsize=10, labelpad=8)
            legend = self.plot_ax.legend(
                facecolor=self.SURFACE_COLOR, edgecolor=self.SPINE_COLOR,
                labelcolor=self.TEXT_COLOR, fontsize=9, fancybox=True,
                framealpha=0.85, borderpad=0.8, handlelength=1.5
            )
            legend.get_frame().set_linewidth(0.5)
        else:
            self.plot_ax.text(
                0.5, 0.5, 'No data yet', transform=self.plot_ax.transAxes,
                ha='center', va='center', color=self.TEXT_COLOR, fontsize=13,
                fontstyle='italic', alpha=0.6
            )

        self.plot_fig.tight_layout(pad=1.5)
        self.plot_canvas_agg.draw()

    def _on_canvas_resize(self, event):
        if self.plot_fig and event.width > 1 and event.height > 1:
            dpi = self.plot_fig.get_dpi()
            self.plot_fig.set_size_inches(event.width / dpi, event.height / dpi)
            self.plot_fig.tight_layout(pad=1.5)
            self.plot_canvas_agg.draw()

    def handle_events(self, event, values):
        retVal = True
        if event == sg.WIN_CLOSED:
            retVal = False
        elif event == '-MCU-':
            selected = values['-MCU-']
            if selected in self.supported_mcu_list:
                self.current_mcu = selected
                self.mcu_filter_string = ""
            else:
                self._window['-MCU-'].update(value=self.current_mcu if hasattr(self, 'current_mcu') else '')
        elif event == '-MCU-KEYRELEASE-':
            self.mcu_filter_string = values['-MCU-']
            self.mcu_list_last_update_time = time.time()
        elif event == '-CONNECT-':
            try:
                selected_mcu = self._window['-MCU-'].get()
                self._update_mcu_history(selected_mcu)
                selected_interface = self._window['-INTERFACE-'].get()
                self.last_interface = selected_interface
                self._save_config()
                if self._rtt_handler.connect(selected_mcu, interface=selected_interface):
                    self._update_gui_status(True)
            except Exception as e:
                sg.popup_error(str(e))
        elif event == '-DISCONNECT-':
            self._rtt_handler.disconnect()
            self._update_gui_status(False)
        elif event == '-CLEAR-':
            self.log_handler['clear']()
            self.log_view.clear_log()
            self.series_data = {}  # Clear all series data
            self._update_series_values_view()
        elif event == '-CLEAR_DATA-':
            self.series_data = {}
            self._last_plot_data_lengths = {}
            self._last_series_values_content = ""
            self._window['-SERIES_VALUES-'].update('')
            self._update_plot()
        elif event == '-SAVE-':
            # Open a file save dialog
            save_path = sg.popup_get_file('Save log', save_as=True, no_window=False, default_extension='txt')
            if save_path:
                try:
                    # Retrieve raw log lines from the log_controller module
                    raw_lines = getattr(log_controller, 'old_raw_log_lines', [])
                    with open(save_path, 'w', encoding='utf-8') as f:
                        for line, _ in raw_lines:
                            f.write(line + '\n')
                except Exception as e:
                    sg.popup_error(f'Failed to save log: {e}')
        elif event == '-FILTER-':
            self.filter_input_string = values['-FILTER-']
        elif event == '-HIGHLIGHT-':
            # Update the log display when filter or highlight changes
            self.highlight_input_string = values['-HIGHLIGHT-']
        elif event == '-PAUSE-':
            # Toggle pause state
            current_text = self._window['-PAUSE-'].GetText()
            new_text = 'Unpause' if current_text == 'Pause' else 'Pause'
            self._window['-PAUSE-'].update(new_text)
            # Trigger update to show accumulated messages if unpaused
            self.log_processing_input_queue.put({"pause_string": new_text})
        elif event in ("-PLOT_SERIES_1-", "-PLOT_SERIES_2-", "-PLOT_SERIES_3-"):
            idx = int(event.split('_')[-1].rstrip('-')) - 1
            selected = values[event]
            self.selected_plot_series[idx] = '' if selected == '—' else selected
            self.active_series_names = [s for s in self.selected_plot_series if s]
            self._last_plot_data_lengths = {}
            self._update_plot()
        elif event == '-ADD_SERIES-':
            name = values['-SERIES_NAME-'].strip()
            pattern = values['-SERIES_PATTERN-'].strip()
            if name and pattern:
                # Check if series name already exists
                if any(s['name'] == name for s in self.data_series):
                    sg.popup_error('A series with this name already exists!')
                else:
                    self.data_series.append({'name': name, 'pattern': pattern})
                    # Auto-activate the new series
                    self.active_series_names = [s['name'] for s in self.data_series]
                    self._update_series_ui()
                    self._window['-ACTIVE_SERIES-'].update(set_to_index=list(range(len(self.data_series))))
                    self.selected_series_for_view = name
                    self._save_config()
                    # Clear input fields
                    self._window['-SERIES_NAME-'].update('')
                    self._window['-SERIES_PATTERN-'].update('')
            else:
                sg.popup_error('Please enter both a name and a pattern!')
        elif event == '-UPDATE_SERIES-':
            name = values['-SERIES_NAME-'].strip()
            pattern = values['-SERIES_PATTERN-'].strip()
            if name and pattern and self.selected_series_for_view:
                # Find the series and update it
                series = next((s for s in self.data_series if s['name'] == self.selected_series_for_view), None)
                if series:
                    old_name = series['name']
                    series['name'] = name
                    series['pattern'] = pattern
                    # Update active series names if the series was active
                    if old_name in self.active_series_names:
                        self.active_series_names[self.active_series_names.index(old_name)] = name
                    # Update stored data key
                    if old_name in self.series_data:
                        self.series_data[name] = self.series_data.pop(old_name)
                    self._update_series_ui()
                    self._save_config()
                    self._window['-SERIES_NAME-'].update('')
                    self._window['-SERIES_PATTERN-'].update('')
                    self.selected_series_for_view = ''
                else:
                    sg.popup_error('Series not found!')
            else:
                sg.popup_error('Select a series from the list first, then enter updated name and pattern!')
        elif event == '-REMOVE_SERIES-':
            selected_indices = self._window['-SERIES_LIST-'].get_indexes()
            if selected_indices:
                index = selected_indices[0]
                removed_series = self.data_series.pop(index)
                # Remove from active series if present
                if removed_series['name'] in self.active_series_names:
                    self.active_series_names.remove(removed_series['name'])
                # Remove stored data for this series
                if removed_series['name'] in self.series_data:
                    del self.series_data[removed_series['name']]
                if self.active_series_names:
                    active_indices = [i for i, s in enumerate(self.data_series) if s['name'] in self.active_series_names]
                    self._update_series_ui()
                    self._window['-ACTIVE_SERIES-'].update(set_to_index=active_indices)
                else:
                    self._update_series_ui()
                self._save_config()
            else:
                sg.popup_error('Please select a series to remove!')
        elif event == '-ACTIVE_SERIES-':
            selected_indices = self._window['-ACTIVE_SERIES-'].get_indexes()
            if selected_indices:
                # Just update the values view, don't modify active_series_names
                self.selected_series_for_view = self.active_series_names[selected_indices[0]]
                self._last_series_values_content = ""
                self._update_series_values_view()
        elif event == '-ACTIVATE_SERIES-':
            selected_indices = self._window['-SERIES_LIST-'].get_indexes()
            if selected_indices:
                name = self.data_series[selected_indices[0]]['name']
                if name not in self.active_series_names:
                    self.active_series_names.append(name)
                    self._update_series_ui()
        elif event == '-DEACTIVATE_SERIES-':
            selected_indices = self._window['-ACTIVE_SERIES-'].get_indexes()
            if selected_indices:
                for idx in sorted(selected_indices, reverse=True):
                    if idx < len(self.active_series_names):
                        self.active_series_names.pop(idx)
                self._update_series_ui()
        elif event == '-SERIES_LIST-':
            # When clicking on a series in the defined list, load its data for editing
            selected_indices = self._window['-SERIES_LIST-'].get_indexes()
            if selected_indices:
                series = self.data_series[selected_indices[0]]
                series_name = series['name']
                series_pattern = series['pattern']
                self.selected_series_for_view = series_name
                self._last_series_values_content = ""
                self._window['-SERIES_NAME-'].update(series_name)
                self._window['-SERIES_PATTERN-'].update(series_pattern)
                self._update_series_values_view()
        return retVal

    def _update_series_ui(self):
        """Update the series listbox and active series listbox"""
        series_names = [s['name'] for s in self.data_series]
        self._window['-SERIES_LIST-'].update(
            values=[f"{s['name']}: {s['pattern']}" for s in self.data_series]
        )
        self._window['-ACTIVE_SERIES-'].update(
            values=self.active_series_names
        )
        combo_values = ['—'] + series_names
        self._window["-PLOT_SERIES_1-"].update(values=combo_values)
        self._window['-PLOT_SERIES_2-'].update(values=combo_values)
        self._window['-PLOT_SERIES_3-'].update(values=combo_values)

    def _update_series_values_view(self):
        """Update the series values view with recorded data"""
        if not self.selected_series_for_view or self.selected_series_for_view not in self.series_data:
            if self._last_series_values_content:
                self._window['-SERIES_VALUES-'].update('')
                self._last_series_values_content = ""
            return

        data = self.series_data[self.selected_series_for_view]
        if not data:
            if self._last_series_values_content != 'No recorded values yet.':
                self._window['-SERIES_VALUES-'].update('No recorded values yet.')
                self._last_series_values_content = 'No recorded values yet.'
            return

        # Format the data for display
        lines = [f"Series: {self.selected_series_for_view}"]
        lines.append(f"Total values: {len(data)}")
        lines.append("-" * 50)
        lines.append(f"{'Timestamp':<20} {'Value':<15}")
        lines.append("-" * 50)

        start_time = data[0][0] if data else 0
        for entry in data:
            timestamp = entry[0]
            value = entry[1]
            relative_time = timestamp - start_time
            lines.append(f"{relative_time:>8.3f}s        {value:>10.3f}")

        content = '\n'.join(lines)
        if content != self._last_series_values_content:
            self._window['-SERIES_VALUES-'].update(content)
            self._window['-SERIES_VALUES-'].Widget.see('end')
            self._last_series_values_content = content

    def run(self):
        # Start log processing thread
        processing_thread = threading.Thread(target=self._log_processing_thread, daemon=True)
        processing_thread.start()

        try:
            # GUI event loop
            while True:
                #time.sleep(0.1)

                # Check events
                event, values = self._window.read(timeout=100)
                if self.handle_events(event, values) == False:
                    break

                # Handle widget highlighting
                input_update = self.log_view.handle_widget_highlighting(
                    self.filter_input_string,
                    self.highlight_input_string,
                    self.mcu_filter_string
                )
                if "mcu_string" in input_update:
                    # Check MCU filter
                    applied_mcu_filter_string = input_update["mcu_string"]
                    if applied_mcu_filter_string:
                        self._filter_mcu_list(applied_mcu_filter_string)

                # Handle log processing on input changes
                if input_update != {}:
                    self.log_processing_input_queue.put(input_update)

                # Update log
                current_time = time.time()
                if current_time - self.last_processed_time >= self.log_update_time_interval_s:
                    self._process_display_output_queue()
                    self.last_processed_time = current_time

                    # Update series values view if a series is selected
                    if self.selected_series_for_view:
                        self._update_series_values_view()

                       # Update plot if a series is selected and data changed
                    plot_series = [s for s in self.selected_plot_series if s]
                    if plot_series:
                        for series_name in plot_series:
                            if series_name in self.series_data:
                                current_len = len(self.series_data[series_name])
                                last_len = self._last_plot_data_lengths.get(series_name, 0)
                                if current_len != last_len:
                                    self._last_plot_data_lengths[series_name] = current_len
                                    self._update_plot()
                                    break

        finally:
            if self.plot_fig:
                plt.close(self.plot_fig)
            self._rtt_handler.disconnect()
            self._window.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='RTT GUI')
    parser.add_argument('--demo-messages', action='store_true', help='Enable demo mode with sample log messages')
    args = parser.parse_args()

    viewer = RTTViewer(demo=args.demo_messages)
    viewer.run()                # Update history on successful connection
