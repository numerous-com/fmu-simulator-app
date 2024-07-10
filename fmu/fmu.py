import fmpy
import pandas as pd
import tempfile
import os


def load_fmu(fmu_file):
    fmu_info = fmpy.dump(fmu_file)

    return fmu_info


def get_variables(fmu_file):
    model_description = fmpy.read_model_description(fmu_file)
    variables = model_description.modelVariables
    return variables, model_description


def run_fmu_simulation(
    fmu_file, config_values, start_time=0.0, stop_time=1.0, step_size=0.1
):

    result = fmpy.simulate_fmu(
        fmu_file,
        start_values=config_values,
        start_time=start_time,
        stop_time=stop_time,
        step_size=step_size,
    )  # , fmi_type="ModelExchange")

    return result


def result_to_pandas(result):
    data = {}
    for row in result:
        for key, value in row.dtype.descr:
            if key not in data:
                data[key] = []
            data[key].append(row[key])
    return pd.DataFrame(data)


def get_setable_variables(fmu_file):
    model_description = fmpy.read_model_description(fmu_file)
    variables = model_description.modelVariables
    setable_variables = []
    for variable in variables:
        print(variable)
        if variable.causality == "input" or variable.causality == "parameter":
            setable_variables.append(variable)
    return setable_variables


def run_simulation_in_process(config_values, filename, duration, step_size):
    # Sort the config values by name
    # config_values = dict(sorted(config_values.items(), key=lambda item: item[0]))

    temp_dir = tempfile.gettempdir()
    fmu_file_path = os.path.join(temp_dir, filename)

    result = run_fmu_simulation(
        fmu_file_path,
        config_values,
        start_time=0.0,
        stop_time=duration,
        step_size=step_size,
    )

    df = result_to_pandas(result)

    return df.to_dict()


if __name__ == "__main__":
    fmu_file = "bouncingBall.fmu"
    config_values = {"g": 9.81, "e": 0.7, "h": 10.0}
    print(get_setable_variables(fmu_file))

    result = run_fmu_simulation(
        fmu_file, config_values, start_time=0.0, stop_time=1.0, step_size=0.1
    )
    df = result_to_pandas(result)
    print(df.head())
    ...
