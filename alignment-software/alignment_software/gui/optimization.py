"""Alignment optimization step module."""


import os
import tkinter as tk
from tkinter import ttk
from tkinter.messagebox import showerror, showinfo, showwarning
from tkinter.filedialog import askopenfilename
import numpy as np
from alignment_software.engine.csv_io import (
    read_single_column_csv, write_columns_csv, write_single_column_csv
)
from .common import NumericSpinbox
from alignment_software.engine.img_io import load_dm3, rewrite_dm3
from alignment_software.engine.img_processing import (
    combine_tranforms,
    convert_img_float64,
    rotate_transform,
    scale_transform,
    transform_img,
    translate_transform
)
from alignment_software.engine.optimization import (
    compute_marker_shifts,
    compute_transformed_shift,
    normalize_marker_data,
    optimize_magnification_and_rotation,
    optimize_particle_model,
    optimize_tilt_angles,
    optimize_x_shift
)


ENTRY_WIDTH = 5


class OptimizationStep:
    """Step that handles optimization."""

    def __init__(
        self, main_window, loading_step, contrast_step, transform_step,
        coarse_align_step, marker_container
    ):
        """
        Create optimization step.
        Depends on loading step to get the output path.
        Depends on contrast step to apply contrast adjustments to preview.
        Depends on transform step to get bulk transform to be combined.
        Depends on coarse alignment to get the shifts from coarse alignment.
        Depends on marker container for particle data.
        """
        self.main_window = main_window
        self.loading_step = loading_step
        self.contrast_step = contrast_step
        self.transform_step = transform_step
        self.coarse_align_step = coarse_align_step
        self.marker_container = marker_container
        self.marker_data = None
        self.aligned_count = 0

    def open(self, close_callback):
        """Opens the step and calls close_callback when done."""

        self.marker_data, partial = self.marker_container.get_complete()
        if len(partial) > 0:
            showwarning(
                "Incomplete marker data",
                "particles with incomplete data %s" %
                str([p+1 for p in partial])
            )
        if len(self.marker_data) < 3:
            showerror(
                "Insufficient marker data",
                "at-least 3 particles with complete data are required"
            )
            close_callback(reset=True)
            return

        self.optimization_window = OptimizationWindow(self.main_window)

        tilt_csv = os.path.join(
            self.loading_step.get_output_path(),
            "tilt_angle.csv"
        )
        self.optimization_window.settings.csv_path_var.set(tilt_csv)

        def close():
            self.optimization_window.destroy()
            self.optimization_window = None
            close_callback(reset=True)

        self.optimization_window.protocol("WM_DELETE_WINDOW", close)

        self.optimization_window.optimize_button.config(
            command=self.perform_optimization
        )

    def load_image(self, i):
        """Load an aligned image output by this step."""
        output_path = self.loading_step.get_output_path()
        filename = f"aligned_{i+1:03d}.dm3"
        filepath = os.path.join(output_path, filename)
        return load_dm3(filepath)

    def image_count(self):
        """Returns the number of frames in the sequence."""
        return self.loading_step.image_count()

    def select_image(self, i):
        """
        Selects either the raw image or aligned image depending on whether
        alignment has proceeded yet.
        """
        if i < self.aligned_count:
            image = self.load_image(i)
        else:
            image = self.loading_step.load_image(i)
        vmin, vmax = self.contrast_step.get_contrast_range(i)
        image = convert_img_float64(image)
        self.main_window.image_frame.render_image(image, vmin, vmax)
        self.main_window.image_frame.update()

    def perform_optimization(self):
        """Main tomography optimization routine."""
        try:
            # compute paths
            transform_csv = os.path.join(
                self.loading_step.get_output_path(),
                "transform.csv"
            )
            tilt_csv = os.path.join(
                self.loading_step.get_output_path(),
                "tilt_angle.csv"
            )

            # determine optimization settings based on user input
            tilt_mode = self.optimization_window.settings.tilt_var.get()
            if tilt_mode == "csv":
                tilt_csv = self.optimization_window.settings.csv_path_var.get()
                tilt = np.array(read_single_column_csv(tilt_csv))
            elif tilt_mode == "constant":
                start = self.optimization_window.settings.start_angle.get()
                step = self.optimization_window.settings.step_angle.get()
                tilt = np.arange(self.image_count()) * step + start
            if self.optimization_window.operations.azimuth_var.get():
                phai = None
                fixed_phai = False
            else:
                phai = 0
                fixed_phai = True
            opmode = self.optimization_window.operations.operation_var.get()
            if opmode == "fixrot-fixmag":
                alpha = self.optimization_window.operations.input_angle.get()
            else:
                alpha = None
            if opmode == "onerot-fixmag":
                group_rotation = False
                group_magnification = False
            if opmode == "onerot-groupmag":
                group_rotation = False
                group_magnification = True
            if opmode == "grouprot-groupmag":
                group_rotation = True
                group_magnification = True

            # find x, y, z locations for each particle
            markers = self.marker_data
            normalized_markers = normalize_marker_data(markers)
            x, y, z, alpha, phai, accuracy = optimize_particle_model(
                normalized_markers, tilt, phai, alpha
            )

            # optimize magnification and rotation if needed
            if opmode == "fixrot-fixmag":
                mag = 1
            else:
                (
                    mag, alpha, phai, accuracy
                ) = optimize_magnification_and_rotation(
                    normalized_markers, x, y, z, tilt, alpha, phai,
                    fixed_phai, group_rotation, group_magnification
                )

            # adjust tilt angles if chosen
            if self.optimization_window.operations.tilt_group_var.get():
                tilt, accuracy = optimize_tilt_angles(
                    normalized_markers,
                    x, y, z, tilt, alpha, phai, mag
                )

            # report azimuth angle back to user
            self.optimization_window.operations.azimuth_input_angle.set(phai)

            # report accuracy back to the user
            self.optimization_window.operations.accuracy_result.config(
                text=str(round(accuracy, 3))
            )

            # get some info about the first image
            first_image = self.loading_step.load_image(0)
            height, width = first_image.shape

            # compute shifts
            shifts = compute_marker_shifts(markers, (width, height))
            x_shift = shifts[:, 0]
            y_shift = shifts[:, 1]
            x_shift, y_shift = compute_transformed_shift(
                x_shift, y_shift, alpha, mag
            )
            x_shift = optimize_x_shift(x_shift, tilt)
            mag = np.ones(self.image_count()) * mag
            alpha = np.ones(self.image_count()) * -alpha

            write_single_column_csv(tilt_csv, tilt)
            write_columns_csv(transform_csv, {
                "optimize_x": x_shift,
                "optimize_y": y_shift,
                "optimize_angle": alpha,
                "optimize_scale": mag
            })

            # transport, output and show optimized images
            self.optimization_window.withdraw()
            for i in range(self.image_count()):
                image = self.loading_step.load_image(i)
                transform_matrix = self.transform_step.get_transform(
                    i, (width, height)
                )
                coarse_matrix = self.coarse_align_step.get_transform(
                    i, self.transform_step.get_binning_factor()
                )
                optimization_transform = combine_tranforms(
                    scale_transform(mag[i], width/2, height/2),
                    rotate_transform(alpha[i], width/2, height/2),
                    translate_transform(x_shift[i],  y_shift[i])
                )
                overall_transform = combine_tranforms(
                    transform_matrix, coarse_matrix, optimization_transform
                )
                image = transform_img(
                    image, overall_transform, image.mean()
                )
                self.save_image(image, i)
                self.aligned_count = i + 1
                self.main_window.image_select.set(i+1)
                self.main_window.update()

            showinfo("Optimization", "Optimization Completed!")
            self.main_window.image_select.set(1)
        except Exception as e:
            showerror("Optimized Alignment Error", str(e))
        finally:
            self.optimization_window.deiconify()

    def save_image(self, image, i):
        """Saves a new dm3 file rewritten with same tag data."""
        output_path = self.loading_step.get_output_path()
        filename = f"aligned_{i+1:03d}.dm3"
        rewrite_dm3(
            self.loading_step.get_path(i),
            os.path.join(output_path, filename),
            image
        )

    def focus(self):
        """Brings the optimization window to the top."""
        self.optimization_window.lift()


class OptimizationWindow(tk.Toplevel):
    """The main tomography optimization window."""

    def __init__(self, master):
        """Create the window."""
        super().__init__(master)
        self.title("Optimization Window")
        self.resizable(False, False)

        self.settings = OptimizationSettingsFrame(self)
        self.settings.grid(row=0, column=0, sticky="nwse")

        self.operations = OperationsFrame(self, text="Operations")
        self.operations.grid(row=1, column=0, sticky="nwse")

        self.optimize_button = ttk.Button(self, text="Optimize")
        self.optimize_button.grid(row=2, column=0, sticky="nwse")


class OperationsFrame(tk.LabelFrame):
    """Frame containing optmization operation settings."""

    def __init__(self, master, text):
        """Create the frame."""
        super().__init__(master, text=text, bd=1)
        self.columnconfigure(0, weight=1)

        self.operation_var = tk.StringVar(self, "fixrot-fixmag")

        fixed_rotation = tk.Radiobutton(
            self, text="Fixed rotation and magnification:",
            value="fixrot-fixmag", variable=self.operation_var
        )
        fixed_rotation.grid(row=0, column=0, sticky="w")
        one_rotation = tk.Radiobutton(
            self, text="One rotation and fixed magnification",
            value="onerot-fixmag", variable=self.operation_var
        )
        one_rotation.grid(row=1, column=0, sticky="w")
        groupm_one_rotation = tk.Radiobutton(
            self, text="Group magnifications and one rotation",
            value="onerot-groupmag", variable=self.operation_var
        )
        groupm_one_rotation.grid(row=2, column=0, sticky="w")

        groupm_group_rotation = tk.Radiobutton(
            self, text="Group magnifications and group rotations",
            value="grouprot-groupmag", variable=self.operation_var
        )
        groupm_group_rotation.grid(row=3, column=0, sticky="w")

        self.input_angle = NumericSpinbox(
            self, value_default=0, value_range=(0, 360), value_type=float,
            width=ENTRY_WIDTH
        )
        self.input_angle.grid(row=0, column=1)

        self.azimuth_var = tk.BooleanVar(self, False)
        azimuth_check = tk.Checkbutton(
            self, text="Adjust azimuth angle amount:",
            variable=self.azimuth_var
        )
        azimuth_check.grid(row=4, column=0, sticky="w")
        self.azimuth_input_angle = NumericSpinbox(
            self, value_default=0, value_range=(0, 360), value_type=float,
            width=ENTRY_WIDTH
        )
        self.azimuth_input_angle.grid(row=4, column=1)

        self.tilt_group_var = tk.BooleanVar(self, False)
        group_tilt_angles = tk.Checkbutton(
            self, text="Group tilt angles", variable=self.tilt_group_var
        )
        group_tilt_angles.grid(row=5, column=0, sticky="w")

        accuracy_label = tk.Label(self, text="Accuracy")
        accuracy_label.grid(row=6, column=0, sticky="e")
        self.accuracy_result = tk.Label(
            self, text="0", bd=1, relief="solid",
            bg="white", fg="black", width=ENTRY_WIDTH
        )
        self.accuracy_result.grid(row=6, column=1)


class OptimizationSettingsFrame(tk.LabelFrame):
    """Frame containing tilt angle settings."""

    def __init__(self, master):
        """Create the frame."""
        super().__init__(master, text="Optimization Settings", bd=1)
        self.columnconfigure(2, weight=1)

        self.tilt_var = tk.StringVar(self, "constant")
        self.tilt_var.trace('w', lambda a, b, c: self.update_selection())
        constant_step = tk.Radiobutton(
            self, text="Constant step", value="constant",
            variable=self.tilt_var
        )
        constant_step.grid(row=0, column=0, sticky="w")
        csv_file = tk.Radiobutton(
            self, text="Csv file", value="csv", variable=self.tilt_var
        )
        csv_file.grid(row=1, column=0, sticky="w")

        start_angle_label = tk.Label(self, text="Start angle:")
        start_angle_label.grid(row=0, column=2)
        self.start_angle = NumericSpinbox(
            self, value_default=0, value_range=(0, 360), value_type=float,
            width=ENTRY_WIDTH
        )
        self.start_angle.grid(row=0, column=3)

        step_angle_label = tk.Label(self, text="Step angle:")
        step_angle_label.grid(row=1, column=2)
        self.step_angle = NumericSpinbox(
            self, value_default=3, value_range=(0, 60), value_type=float,
            width=ENTRY_WIDTH
        )
        self.step_angle.grid(row=1, column=3)

        self.csv_button = ttk.Button(
            self, text="open csv", command=self.open_csv
        )
        self.csv_button.grid(row=2, column=0, columnspan=2, sticky="we")
        self.csv_path_var = tk.StringVar(self, "")
        self.csv_entry = ttk.Entry(self, textvariable=self.csv_path_var)
        self.csv_entry.grid(row=2, column=2, columnspan=2, sticky="we")
        self.update_selection()

    def update_selection(self):
        """Called when tilt mode is changed."""
        tilt_mode = self.tilt_var.get()
        if tilt_mode == "csv":
            self.csv_button.config(state="normal")
            self.csv_entry.config(state="normal")
        else:
            self.csv_button.config(state="disabled")
            self.csv_entry.config(state="disabled")

    def open_csv(self):
        """Prompts the user to enter a csv."""
        filename = askopenfilename(filetypes=[("CSV File", "*.csv")])
        if filename:
            self.csv_path_var.set(filename)
