import panel as pn
import os
import logging
from fmu.fmu import get_variables, run_simulation_in_process
from concurrent.futures import ProcessPoolExecutor
import pandas as pd
import time
import tempfile

# Create a ProcessPoolExecutor to run the simulation in a separate process, so we can control the execution time
process_executor = ProcessPoolExecutor()

# Set up logging for the app
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def display_fmu_info(fmu_info):
    info_pane = pn.pane.Markdown(fmu_info)
    return info_pane


def create_fmu_configuration_widgets(variables, model_description):

    config_widgets = []
    parameter_widgets = []
    state_widgets = []

    # Create widgets for the simulation duration and step size
    duration_widget = pn.widgets.FloatInput(
        name="Duration (s)", value=1.0, start=0.1, end=1000.0
    )
    step_size_widget = pn.widgets.FloatInput(
        name="Step Size (s)",
        value=(
            model_description.defaultExperiment.stepSize
            if model_description.defaultExperiment
            else 0.1
        ),
    )
    time_widgets = [duration_widget, step_size_widget]

    for variable in variables:
        # Add widgets for inputs, state start values and parameters:
        if (
            variable.causality == "input"
            or variable.causality == "parameter"
            or variable.causality == "local"
        ):
            widget = None
            if variable.type == "Real":
                widget = pn.widgets.FloatInput(
                    name=variable.name,
                    value=float(variable.start) if variable.start else 0.0,
                )
            elif variable.type == "Integer":
                widget = pn.widgets.IntInput(
                    name=variable.name,
                    value=int(variable.start) if variable.start else 0,
                )
            elif variable.type == "Boolean":
                widget = pn.widgets.Checkbox(
                    name=variable.name, value=variable.start or False
                )
            elif variable.type == "String":
                widget = pn.widgets.TextInput(
                    name=variable.name, value=variable.start if variable.start else ""
                )

            if widget:
                logger.debug("Adding widget for variable: %s", variable.name)
                if variable.causality == "input":
                    config_widgets.append(widget)
                elif variable.causality == "parameter":
                    parameter_widgets.append(widget)
                elif variable.causality == "local" and variable.start is not None:
                    state_widgets.append(widget)

    if not config_widgets:
        logger.warning("No input variables found in the FMU.")

    return config_widgets, parameter_widgets, state_widgets, time_widgets


# Explantory text to guide the user to upload an FMU file
explanation_text = pn.pane.Markdown(
    """
This app allows you to upload an FMU file and configure the simulation parameters.
After uploading the FMU file, you can set the start, stop and step size for the simulation, as well as the input variables.
Note: If you don't have an FMU file, you can download this one to try the app: [ControlledTemperature](https://github.com/modelica/fmi-cross-check/raw/master/fmus/2.0/cs/linux64/MapleSim/2021.2/ControlledTemperature/ControlledTemperature.fmu).
"""
)

# File input widget to upload the FMU file
file_input = pn.widgets.FileInput(name="Upload FMU File", accept=".fmu")

# Variables to store the widgets for the configuration
output_names = []
config_widgets = []
parameter_widgets = []
state_widgets = []
time_widgets = []
state_enable_widgets = []
result_pane = pn.Column()

start_button = pn.widgets.Button(name="Run Simulation", button_type="primary")


def on_file_upload(event):
    """Callback function to handle the file upload event"""

    temp_dir = tempfile.gettempdir()
    fmu_file_path = os.path.join(temp_dir, event.obj.filename)

    with open(fmu_file_path, "wb") as f:
        f.write(event.new)

    variables, model_description = get_variables(fmu_file_path)

    config_widgets[:], parameter_widgets[:], state_widgets[:], time_widgets[:] = (
        create_fmu_configuration_widgets(variables, model_description)
    )

    # Create a row for each state widget and an enable checkbox
    state_enable_widgets[:] = [
        pn.Row(state_widget, pn.widgets.Checkbox(name=" set", value=False))
        for state_widget in state_widgets
    ]

    app_content[:] = (
        [explanation_text, file_input]
        + config_widgets
        + [pn.Card(*parameter_widgets, title="Parameters")]
        + [pn.Card(*state_enable_widgets, title="Initial Conditions")]
        + [pn.Card(*time_widgets, title="Simulation")]
    )
    result_pane.clear()
    result_pane.append(start_button)
    output_names[:] = [
        variable.name
        for variable in variables
        if variable.causality in ["output", "local", "calculated", "input"]
    ]


# Add the callback function to the file input widget
file_input.param.watch(on_file_upload, "value")


def on_start_button_click(event):
    """Callback function to handle the start button click event"""

    state_widgets_enabled = [w[0] for w in state_enable_widgets if w[1].value]
    config_values = {
        w.name: w.value
        for w in config_widgets + parameter_widgets + state_widgets_enabled
    }

    simulation_failed = False

    result_pane.clear()

    # Add a loading spinner while the simulation is running
    result_pane.append(
        pn.indicators.LoadingSpinner(value=True, size=20, name="Simulatin running...")
    )

    try:
        future = process_executor.submit(
            run_simulation_in_process,
            config_values,
            file_input.filename,
            time_widgets[0].value,
            time_widgets[1].value,
        )

        # Wait a max of 10 seconds for the simulation to finish, otherwise display stop the simulation and display an error message

        started = time.time()
        elapsed_time = 0
        dt = 0.1

        while not future.done() and elapsed_time < 10:
            time.sleep(dt)
            elapsed_time = time.time() - started

        if not future.done():
            # Cancel the simulation if it's still running
            future.cancel()
            result_pane.clear()
            result_pane.append(
                pn.pane.Alert(
                    "Simulation took too long to run. Please try again.",
                    alert_type="warning",
                )
            )
            simulation_failed = True
        else:
            # Get the result of the simulation
            result = future.result()

    except Exception as e:
        # Display the error message
        result_pane.clear()
        result_pane.append(start_button)
        result_pane.append(
            pn.pane.Alert(f"Error running simulation: {e}", alert_type="danger")
        )
        simulation_failed = True

    if not simulation_failed:
        result_pane.clear()
        result_pane.append(start_button)

        # Save the result to a CSV file
        filename = "simulation_result.csv"

        df = pd.DataFrame(result)
        df.to_csv(filename, index=False)

        # Define the callback function for the FileDownload widget
        def get_file():
            return filename

        # Create the FileDownload widget
        download_link = pn.widgets.FileDownload(
            filename=filename,
            callback=get_file,
            button_type="primary",
            label="Download Simulation Result",
        )

        # Make a line plot where time is the x-axis
        cols_no_time = list(df.columns)
        cols_no_time.remove("time")
        plot = df.hvplot.line(
            x="time",
            y=cols_no_time,
            width=800,
            height=400,
            title="Simulation Results",
            legend="top_left",
            xlabel="Time (s)",
            ylabel="Value",
        )

        result_pane.append(pn.Column(*[plot, download_link]))


# Add the callback function to the start button
start_button.on_click(on_start_button_click)

# Create the app content
app_content = pn.Column(explanation_text, file_input)

app = pn.template.MaterialTemplate(
    title="FMU Simulator App",
    main=[app_content, result_pane],
)

app.servable()
