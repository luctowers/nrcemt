"""Contrast adjustment step module."""


import os
import numpy as np
import tkinter as tk
from tkinter import ttk
from tkinter.messagebox import showerror
import matplotlib.patches as patches
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from .common import AsyncHandler
from alignment_software.engine.csv_io import (
    read_columns_csv, write_columns_csv
)
from alignment_software.engine.img_processing import (
    adjust_img_range,
    convert_img_float64,
    reject_outliers_percentile
)

INPUT_WIDTH = 10
PADDING = 4


class ContrastStep:
    """Step that applies contrast adjustments."""

    def __init__(self, main_window, loading_step):
        """
        Create contrast step.
        Depends on loading step to get raw images.
        """
        self.main_window = main_window
        self.loading_step = loading_step
        self.contrast_window = None
        self.contrast_ranges = None
        self.reset()

    def open(self, close_callback):
        """Opens the step and calls close_callback when done."""
        self.contrast_window = ContrastWindow(self.main_window)

        def close():
            self.save()
            self.contrast_window.destroy()
            self.contrast_window = None
            close_callback(reset=True)

        self.contrast_window.protocol("WM_DELETE_WINDOW", close)

        self.contrast_window.tools.apply.config(
            command=self.apply_outlier_rejection
        )
        slider_handler = AsyncHandler(self.handle_sliders)
        self.contrast_window.tools.slider_min.config(
            command=slider_handler
        )
        self.contrast_window.tools.slider_max.config(
            command=slider_handler
        )

    def save(self):
        """Saves contrast ranges to transform csv."""
        transform_csv = os.path.join(
            self.loading_step.get_output_path(),
            "transform.csv"
        )
        if self.contrast_ranges is None:
            write_columns_csv(transform_csv, {
                "contrast_min": [], "contrast_max": []
            })
        else:
            write_columns_csv(transform_csv, {
                "contrast_min": self.contrast_ranges[:, 0],
                "contrast_max": self.contrast_ranges[:, 1]
            })

    def restore(self):
        """Restore from transform csv."""
        transform_csv = os.path.join(
            self.loading_step.get_output_path(),
            "transform.csv"
        )
        try:
            restored_contrast = read_columns_csv(
                transform_csv, ["contrast_min", "contrast_max"]
            )
            if len(restored_contrast["contrast_min"]) != self.image_count():
                return False
            if len(restored_contrast["contrast_min"]) != self.image_count():
                return False
            self.contrast_ranges = np.empty((self.image_count(), 2))
            self.contrast_ranges[:, 0] = restored_contrast["contrast_min"]
            self.contrast_ranges[:, 1] = restored_contrast["contrast_max"]
            return True
        except FileNotFoundError:
            return False
        except KeyError:
            return False

    def load_image(self, i):
        """Load image, either raw or contrast adjusted."""
        image = self.loading_step.load_image(i)
        image = convert_img_float64(image)
        if self.contrast_ranges is not None:
            vmin, vmax = self.contrast_ranges[i]
            image = adjust_img_range(image, vmin, vmax, 0.0, 1.0)
        return image

    def get_contrast_range(self, i):
        """Get contrast range as a tuple."""
        if self.contrast_ranges is None:
            return None, None
        else:
            return self.contrast_ranges[i]

    def image_count(self):
        """Returns the number of frames in the sequence."""
        return self.loading_step.image_count()

    def select_image(self, i):
        """Render image and update histogram."""
        raw_image = self.loading_step.load_image(i)
        float_image = convert_img_float64(raw_image)
        if self.contrast_ranges is None:
            vmin, vmax = 0.0, 1.0
        else:
            vmin, vmax = self.contrast_ranges[i]
        if self.contrast_window is not None:
            self.contrast_window.histogram.render_histogram(float_image)
            self.contrast_window.histogram.render_range(vmin, vmax)
        self.main_window.image_frame.render_image(float_image, vmin, vmax)
        self.main_window.image_frame.update()

    def reset(self):
        """Erase the contrast ranges."""
        self.contrast_ranges = None

    def is_ready(self):
        """Contrast step is ready if loading step is ready, regardless."""
        return self.loading_step.is_ready()

    def apply_outlier_rejection(self):
        """Apply percentile outlier rejection."""
        try:
            percentile = self.contrast_window.tools.percentile_var.get()
        except Exception as e:
            showerror("Contrast Error", str(e))
            return
        self.contrast_window.progress_var.set(0)
        self.contrast_window.update_idletasks()
        apply_per_image = self.contrast_window.tools.discrete_var.get()
        image_count = self.image_count()
        selected_image = self.main_window.selected_image()
        if apply_per_image:
            self.contrast_ranges = np.empty((image_count, 2))
            for i in range(image_count):
                image = self.loading_step.load_image(i)
                image = convert_img_float64(image)
                self.contrast_ranges[i] = (
                    reject_outliers_percentile(image, percentile)
                )
                self.contrast_window.progress_var.set(i / (image_count-1))
                self.contrast_window.update_idletasks()
        else:
            image = self.loading_step.load_image(selected_image)
            image = convert_img_float64(image)
            contrast_range = reject_outliers_percentile(image, percentile)
            self.contrast_ranges = np.array(image_count * [contrast_range])
        self.contrast_window.progress_var.set(1)
        self.select_image(selected_image)

    def handle_sliders(self, value):
        """Handle contrast sliders updating."""
        vmin = self.contrast_window.tools.slider_min.get()
        vmax = self.contrast_window.tools.slider_max.get()
        self.contrast_ranges = np.array(self.image_count() * [[vmin, vmax]])
        self.select_image(self.main_window.selected_image())

    def focus(self):
        """Brings the contrast window to the top."""
        self.contrast_window.lift()


class ContrastWindow(tk.Toplevel):
    """Contrast window with histogram and tools for contrast adjustment."""

    def __init__(self, master):
        """Creates the window."""
        super().__init__(master)
        self.title("Contrast Adjustment Window")
        self.geometry("360x360")
        self.minsize(360, 360)

        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self.tools = ContrastToolFrame(self)
        self.tools.grid(row=0, column=0, sticky="w")
        self.histogram = HistogramFrame(self)
        self.histogram.grid(row=1, column=0, sticky="nswe")
        self.progress_var = tk.DoubleVar(value=0.0)
        progress = ttk.Progressbar(
            self, orient="horizontal", variable=self.progress_var, max=1.0
        )
        progress.grid(row=2, column=0, sticky="we")


class ContrastToolFrame(tk.Frame):
    """Frame for the controls at the top of the contrast window."""

    def __init__(self, master):
        """Create the frame."""
        super().__init__(master)

        # Frame for Data Range
        data_frame = tk.LabelFrame(self, bd=1, text="Data Range")
        data_frame.grid(row=0, column=0, sticky="nwse")

        # Frame for Scale Display Range
        scale_frame = tk.LabelFrame(self, bd=1, text="Scale Display")
        scale_frame.grid(row=0, column=1, sticky="nwse")

        # Minimum data
        min_label = ttk.Label(scale_frame, text="Minimum:")
        min_label.grid(row=0, column=0, pady=PADDING)
        min_range = tk.Frame(scale_frame)
        self.min_range_val = ttk.Label(min_range, text="0")
        self.min_range_val.pack()
        min_range.grid(row=0, column=1, pady=PADDING)

        # Max Data
        max_label = ttk.Label(scale_frame, text="Maximum:")
        max_label.grid(row=1, column=0, pady=PADDING)
        max_range = tk.Frame(scale_frame)
        self.max_range_val = ttk.Label(max_range, text="1")
        self.max_range_val.pack()
        max_range.grid(row=1, column=1, pady=PADDING)

        self.discrete_var = tk.BooleanVar(value=True)
        apply_discretely = ttk.Checkbutton(
            data_frame, text="Adjust discretely",
            variable=self.discrete_var
        )
        apply_discretely.grid(row=1, column=0)

        eliminate_outliers = ttk.Label(data_frame, text="Rejection percentile")
        eliminate_outliers.grid(row=0, column=0)
        self.percentile_var = tk.DoubleVar(value=2.0)
        outlier_percentile = ttk.Entry(
            data_frame, textvariable=self.percentile_var, width=INPUT_WIDTH
        )
        outlier_percentile.grid(row=0, column=1)

        slider_frame = tk.LabelFrame(self, bd=1, text="Manual adjustment")
        slider_frame.grid(row=1, column=0, columnspan=2)
        label_min = ttk.Label(slider_frame, text="min: ")
        label_min.grid(row=0, column=0)
        self.slider_min = ttk.Scale(slider_frame, length=300, value=0.0)
        self.slider_min.grid(row=0, column=1)
        label_max = ttk.Label(slider_frame, text="max: ")
        label_max.grid(row=1, column=0)
        self.slider_max = ttk.Scale(slider_frame, length=300, value=1.0)
        self.slider_max.grid(row=1, column=1)

        self.apply = ttk.Button(data_frame, text="Apply")
        self.apply.grid(row=1, column=1)


class HistogramFrame(tk.Frame):
    """Frame for the histogram in the contrast window."""

    def __init__(self, master, **kwargs):
        """Create the frame."""
        super().__init__(master, **kwargs)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.figure = Figure(figsize=(8, 8), dpi=100)
        self.axis = self.figure.add_subplot()
        self.canvas = FigureCanvasTkAgg(self.figure, self)
        self.canvas.get_tk_widget().grid(column=0, row=0, sticky="nwse")
        self.patch = None
        self.hist = None

    def render_histogram(self, image):
        """Render the histogram given image data."""
        image_flat = image.ravel()
        image_max = image.max()
        self.axis.clear()
        self.axis.hist(image_flat, bins=100, range=(0, image_max))
        self.axis.xaxis.set_ticks(
            [0.0, 0.25*image_max, 0.5*image_max, 0.75*image_max, image_max],
            labels=["0.0", "0.25", "0.5", "0.75", "1.0"]
        )
        self.axis.get_yaxis().set_visible(False)
        self.canvas.draw()

    def render_range(self, vmin, vmax):
        """Render a box indication contrast range."""
        if self.patch is not None:
            self.patch.remove()
        self.patch = patches.Rectangle(
            (vmin, 0.1),
            vmax-vmin, 0.8,
            linewidth=1,
            edgecolor='r',
            facecolor='none',
            transform=self.axis.get_xaxis_transform()
        )
        self.axis.add_patch(self.patch)
        self.canvas.draw()
