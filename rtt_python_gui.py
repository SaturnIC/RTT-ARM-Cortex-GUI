import FreeSimpleGUI as sg
import json
import os
import time
import queue
import threading
import argparse
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
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
        sg.theme('Dark Gray 13')

        # Create layout with new filter, highlight, and pause elements
        log_tab = [
            [sg.Multiline(size=(80, 20), key='-LOG-', expand_x=True, expand_y=True, font=('Consolas', 10))],
            [sg.Column([
                [sg.Text('Filter:'),
                 sg.Input(key='-FILTER-', size=(20, 1), enable_events=True),
                 sg.Text('Highlight:'),
                 sg.Input(key='-HIGHLIGHT-', size=(20, 1), enable_events=True),
                 sg.Button('Pause', key='-PAUSE-', disabled=False),
                 sg.Button('Clear', key='-CLEAR-'),
                 sg.Button('Save', key='-SAVE-')]
            ])]
        ]

        # Data Series tab
        data_series_tab = [
            [sg.Text('Data Series Configuration', font=('Arial', 12, 'bold'))],
            [sg.HorizontalSeparator()],
            [sg.Text('Series Name:'), sg.Input(key='-SERIES_NAME-', size=(25, 1))],
            [sg.Text('Pattern (<N>=capture number, *=wildcard):'), sg.Input(key='-SERIES_PATTERN-', size=(40, 1))],
            [sg.Button('Add Series', key='-ADD_SERIES-'), sg.Button('Update Series', key='-UPDATE_SERIES-'), sg.Button('Remove Series', key='-REMOVE_SERIES-')],
            [sg.HorizontalSeparator()],
            [sg.Column([
                [sg.Text('Defined Series:', font=('Arial', 10, 'bold'))],
                [sg.Listbox(values=[f"{s['name']}: {s['pattern']}" for s in self.data_series],
                           key='-SERIES_LIST-', size=(40, 8), select_mode=sg.LISTBOX_SELECT_MODE_SINGLE, enable_events=True)]
            ]),
            sg.Column([
                [sg.Text('Active Series (Ctrl+Click to select multiple):', font=('Arial', 10, 'bold'))],
                [sg.Listbox(values=[s['name'] for s in self.data_series],
                           key='-ACTIVE_SERIES-', size=(25, 8), select_mode=sg.LISTBOX_SELECT_MODE_EXTENDED, enable_events=True)]
            ])],
            [sg.HorizontalSeparator()],
            [sg.Text('Recorded Values for Selected Series:', font=('Arial', 10, 'bold'))],
            [sg.Multiline(size=(70, 10), key='-SERIES_VALUES-', expand_x=True, font=('Consolas', 9))]
        ]

        plot_tab = [
            [sg.Text('Glob Pattern:'), sg.Input(key='-PLOT_PATTERN-', size=(40, 1), enable_events=True), sg.Button('Update Plot', key='-UPDATE_PLOT-')],
            [sg.Canvas(key='-CANVAS-', size=(640, 480))]
        ]

        self._layout = [
            [sg.Text('ARM Cortex RTT GUI', size=(20, 1), justification='center')],
            [sg.Frame('Configuration', [
                [sg.Text('MCU Chip Name:', size=(14, 1)),
                sg.Text("", size=(1, 1)),  # horizontal spacer
                sg.Combo(self._build_mcu_combo_values(),
                        default_value='DEMO_MCU' if demo else 'STM32F427II',
                        key='-MCU-', size=(20, 1), enable_events=True, auto_size_text=False)],
                [sg.Text('Interface:', size=(14, 1)),
                sg.Text("", size=(1, 1)),  # horizontal spacer
                sg.Combo(['SWD', 'JTAG'], default_value=self.last_interface,
                        key='-INTERFACE-', size=(10, 1), auto_size_text=False)],
                ], pad=((10,30),(10,10))),
            sg.Frame('Connection', [
                [sg.Button('Connect', key='-CONNECT-'),
                sg.Button('Disconnect', key='-DISCONNECT-', disabled=True)],
                [sg.Text('Status: Disconnected', key='-STATUS-', size=(20, 1))]
                ], pad=((20,10),(10,10)))
            ],
            [sg.TabGroup([
                [sg.Tab('Log', log_tab, key='-LOG_TAB-'),
                 sg.Tab('Data Series', data_series_tab, key='-DATA_SERIES_TAB-'),
                 sg.Tab('Plot', plot_tab, key='-PLOT_TAB-')]
            ], expand_x=True, expand_y=True)]
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
        self.plot_pattern = ""
        self.active_series_names = []
        self.series_data = {}  # Dictionary to store recorded values for each series
        self.selected_series_for_view = ""  # Currently selected series for viewing values

        # Initialize plot
        self._update_plot()

        self.demo = demo

    def _update_gui_status(self, connected):
        self._window['-STATUS-'].update(
            'Status: Connected' if connected else 'Status: Disconnected'
        )
        self._window['-CONNECT-'].update(disabled=connected)
        self._window['-DISCONNECT-'].update(disabled=not connected)
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

    def _update_plot(self):
        canvas_elem = self._window['-CANVAS-']
        canvas = canvas_elem.TKCanvas
        fig = plt.Figure(figsize=(6, 4))
        ax = fig.add_subplot(111)
        has_data = False
        colors = ['b', 'r', 'g', 'm', 'c', 'y', 'k']
        for i, series_name in enumerate(self.active_series_names):
            if series_name in self.series_data and self.series_data[series_name]:
                has_data = True
                data = self.series_data[series_name]
                start_time = data[0][0]
                # data entries: (timestamp, value, group_index)
                values = [d[1] for d in data]
                times = [d[0] - start_time for d in data]
                color = colors[i % len(colors)]
                ax.plot(times, values, label=series_name, color=color, linewidth=1)
        if has_data:
            ax.set_xlabel('Time (s)')
            ax.set_ylabel('Value')
            ax.set_title('Plot Data')
            ax.legend()
            ax.grid(True, alpha=0.3)
        else:
            ax.text(0.5, 0.5, 'No data', transform=ax.transAxes, ha='center', va='center')
        # Clear previous figure
        for item in canvas.winfo_children():
            item.destroy()
        canvas_agg = FigureCanvasTkAgg(fig, master=canvas)
        canvas_agg.draw()
        canvas_agg.get_tk_widget().pack(fill='both', expand=True)
        plt.close(fig)

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
        elif event == '-PLOT_PATTERN-':
            self.plot_pattern = values['-PLOT_PATTERN-']
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
                    self.plot_pattern = pattern
                    self._window['-PLOT_PATTERN-'].update(self.plot_pattern)
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
                # Update plot pattern from first active series if available
                if self.active_series_names:
                    first_active = next((s for s in self.data_series if s['name'] == self.active_series_names[0]), None)
                    if first_active:
                        self.plot_pattern = first_active['pattern']
                        self._window['-PLOT_PATTERN-'].update(self.plot_pattern)
                    # Re-select active series in the listbox
                    active_indices = [i for i, s in enumerate(self.data_series) if s['name'] in self.active_series_names]
                    self._update_series_ui()
                    self._window['-ACTIVE_SERIES-'].update(set_to_index=active_indices)
                else:
                    self.plot_pattern = ""
                    self._window['-PLOT_PATTERN-'].update('')
                    self._update_series_ui()
                self._save_config()
            else:
                sg.popup_error('Please select a series to remove!')
        elif event == '-ACTIVE_SERIES-':
            selected_indices = self._window['-ACTIVE_SERIES-'].get_indexes()
            if selected_indices:
                # Get selected series names
                self.active_series_names = [self.data_series[i]['name'] for i in selected_indices]
                # Update plot pattern from first active series
                if self.active_series_names:
                    first_active = next((s for s in self.data_series if s['name'] == self.active_series_names[0]), None)
                    if first_active:
                        self.plot_pattern = first_active['pattern']
                        self._window['-PLOT_PATTERN-'].update(self.plot_pattern)
                else:
                    self.plot_pattern = ""
                    self._window['-PLOT_PATTERN-'].update('')

                # Update the series values view for the first selected series
                if self.active_series_names:
                    self.selected_series_for_view = self.active_series_names[0]
                    self._update_series_values_view()
        elif event == '-SERIES_LIST-':
            # When clicking on a series in the defined list, load its data for editing
            selected_indices = self._window['-SERIES_LIST-'].get_indexes()
            if selected_indices:
                series = self.data_series[selected_indices[0]]
                series_name = series['name']
                series_pattern = series['pattern']
                self.selected_series_for_view = series_name
                self._window['-SERIES_NAME-'].update(series_name)
                self._window['-SERIES_PATTERN-'].update(series_pattern)
                self._update_series_values_view()
        elif event == '-UPDATE_PLOT-':
            self._update_plot()
        return retVal

    def _update_series_ui(self):
        """Update the series listbox and active series listbox"""
        self._window['-SERIES_LIST-'].update(
            values=[f"{s['name']}: {s['pattern']}" for s in self.data_series]
        )
        self._window['-ACTIVE_SERIES-'].update(
            values=[s['name'] for s in self.data_series]
        )

    def _update_series_values_view(self):
        """Update the series values view with recorded data"""
        if not self.selected_series_for_view or self.selected_series_for_view not in self.series_data:
            self._window['-SERIES_VALUES-'].update('')
            return

        data = self.series_data[self.selected_series_for_view]
        if not data:
            self._window['-SERIES_VALUES-'].update('No recorded values yet.')
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

        self._window['-SERIES_VALUES-'].update('\n'.join(lines))

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

        finally:
            self._rtt_handler.disconnect()
            self._window.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='RTT GUI')
    parser.add_argument('--demo-messages', action='store_true', help='Enable demo mode with sample log messages')
    args = parser.parse_args()

    viewer = RTTViewer(demo=args.demo_messages)
    viewer.run()                # Update history on successful connection
