import tkinter as tk
from tkinter import ttk
from tkinter.messagebox import showwarning
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.patches import Rectangle
import matplotlib.patheffects as pe
from alignment_software.engine.particle_tracking import (
    ParticlePositionContainer
)
from .manual_track import ManualTrackStep
from .common import AsyncHandler
from .contrast import ContrastStep
from .loading import LoadingStep
from .transform import TransformStep
from .coarse_align import CoarseAlignStep
from .auto_track import AutoTrackStep
from .optimization import OptimizationStep
from .frame_steps import StepsFrame
from .frame_sequence_selector import SequenceSelector


class MainWindow(tk.Tk):
    """The main window for alignment software."""

    def __init__(self):
        """Creates the alignment software window."""
        super().__init__()
        self.geometry("800x600")
        self.title("Alignment Main Window")
        self.minsize(600, 450)

        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # populate window contents
        side_frame = tk.Frame()
        side_frame.grid(column=0, row=0, sticky="nswe")
        side_frame.rowconfigure(0, weight=1)
        self.steps = StepsFrame(side_frame)
        self.steps.grid(column=0, row=0, sticky="nwe")
        self.restore_button = ttk.Button(
            side_frame, text="Restore previous session"
        )
        self.restore_button.grid(column=0, row=2, sticky="swe")
        self.image_select = SequenceSelector(side_frame, "Image displayed")
        self.image_select.grid(column=0, row=3, sticky="swe")
        self.image_frame = ImageFrame(self)
        self.image_frame.grid(column=1, row=0)

        # sets the command which gets called when image selector moves.
        self.image_select.set_command(AsyncHandler(
            lambda n: self.select_image(n-1)
        ))

        # sets the command which gets called when image is clicked.
        self.image_frame.set_click_command(self.canvas_click)

        # creates all the necessary steps and injects them as dependecies to
        # eachother
        self.loading_step = LoadingStep(self)
        self.contrast_step = ContrastStep(self, self.loading_step)
        self.transform_step = TransformStep(
            self, self.loading_step, self.contrast_step
        )
        self.coarse_align_step = CoarseAlignStep(
            self,  self.loading_step, self.transform_step
        )
        particle_positions = ParticlePositionContainer()
        self.auto_track_step = AutoTrackStep(
            self, self.loading_step, self.coarse_align_step, particle_positions
        )
        self.manual_track_step = ManualTrackStep(
            self, self.loading_step, self.coarse_align_step, particle_positions
        )
        self.optimization_step = OptimizationStep(
            self, self.loading_step, self.contrast_step, self.transform_step,
            self.coarse_align_step, particle_positions
        )

        # some variables to keep track of the current open step
        self.current_step = None
        self.current_step_open = False

        # configure button restore and open steps
        self.restore_button.config(
            command=self.restore
        )
        self.steps.load_button.config(
            command=lambda: self.open_step(self.loading_step)
        )
        self.steps.contrast_button.config(
            command=lambda: self.open_step(self.contrast_step)
        )
        self.steps.transform_button.config(
            command=lambda: self.open_step(self.transform_step)
        )
        self.steps.coarse_align_button.config(
            command=lambda: self.open_step(self.coarse_align_step)
        )
        self.steps.auto_track_button.config(
            command=lambda: self.open_step(self.auto_track_step)
        )
        self.steps.manual_track_button.config(
            command=lambda: self.open_step(self.manual_track_step)
        )
        self.steps.optimization_button.config(
            command=lambda: self.open_step(self.optimization_step)
        )

        self.update_button_states()

    def open_step(self, step):
        """Opens a step if one isn't in progress"""
        # check if a nother step is currently open
        if self.current_step_open:
            if self.current_step != step:
                showwarning(
                    "Error launching step",
                    "Finish the current step before opening another!"
                )
            if hasattr(self.current_step, 'focus'):
                self.current_step.focus()
            return

        # launch the step and set callback for when it closes
        self.current_step = step
        self.current_step_open = True
        self.current_step.open(lambda reset: self.close_step(step, reset))
        self.select_image(self.selected_image())

    def close_step(self, step, reset):
        """Called when a step is closed."""
        self.current_step_open = False
        if reset and step == self.loading_step:
            self.contrast_step.reset()
        self.update_button_states()

    def update_button_states(self):
        """Sets whether buttons are enabled or disabled."""
        self.restore_button.config(
            state="normal" if self.loading_step.is_ready() else "disabled"
        )
        self.steps.contrast_button.config(
            state="normal" if self.loading_step.is_ready() else "disabled"
        )
        self.steps.transform_button.config(
            state="normal" if self.loading_step.is_ready() else "disabled"
        )
        self.steps.coarse_align_button.config(
            state="normal" if self.loading_step.is_ready() else "disabled"
        )
        self.steps.auto_track_button.config(
            state="normal" if self.coarse_align_step.is_ready() else "disabled"
        )
        self.steps.manual_track_button.config(
            state="normal" if self.coarse_align_step.is_ready() else "disabled"
        )
        self.steps.optimization_button.config(
            state="normal" if self.coarse_align_step.is_ready() else "disabled"
        )

    def restore(self):
        """Asks steps to restore data from a previous session."""
        if self.current_step_open:
            return showwarning(
                "Error restoring",
                "Finish the current step!"
            )
        latest_step = None
        if self.contrast_step.restore():
            latest_step = self.contrast_step
        if self.transform_step.restore():
            latest_step = self.transform_step
        if self.coarse_align_step.restore():
            latest_step = self.coarse_align_step
        if self.auto_track_step.restore():
            latest_step = self.auto_track_step
        self.current_step = latest_step
        self.select_image(self.selected_image())
        self.update_button_states()

    def canvas_click(self, x, y):
        """Let the current step know the window has been clicked."""
        if self.current_step is not None:
            if hasattr(self.current_step, 'canvas_click'):
                self.current_step.canvas_click(x, y)

    def select_image(self, index):
        """Select an image with a zero-base index."""
        if self.current_step is not None:
            self.current_step.select_image(index)

    def selected_image(self):
        """Get the currently selected image with a zero-base index."""
        return self.image_select.get()-1


class ImageFrame(ttk.Frame):
    """Matplotlib canvas for rendering images and marking them up."""

    def __init__(self, master, **kwargs):
        """Create the canvas."""
        super().__init__(master, **kwargs)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.figure = Figure(figsize=(8, 8), dpi=100)
        self.axis = self.figure.add_subplot()
        self.canvas = FigureCanvasTkAgg(self.figure, self)
        self.canvas.get_tk_widget().grid(column=0, row=0, sticky="nwse")
        self.click_command = None
        self.canvas.mpl_connect("button_press_event", self.on_click)
        self.y_min, self.y_max = 0, 0
        self.x_min, self.x_max = 0, 0

    def set_click_command(self, command):
        """Sets the command to be called when the image is clicked."""
        self.click_command = command

    def on_click(self, event):
        """Handle the click event."""
        if self.click_command is not None:
            x, y = self.axis.transData.inverted().transform((event.x, event.y))
            x, y = int(x), int(y)
            if x < self.x_min or x >= self.x_max:
                return
            if y < self.y_min or y >= self.y_max:
                return
            self.click_command(int(x), int(y))

    def render_image(self, img, vmin=0.0, vmax=1.0):
        """Render an image with a given dynamic range."""
        self.axis.clear()
        self.axis.imshow(img, cmap="gray", vmin=vmin, vmax=vmax)
        self.y_max, self.y_min = self.axis.get_ylim()
        self.x_min, self.x_max = self.axis.get_xlim()
        self.axis.set_xlim(self.x_min, self.x_max)
        self.axis.set_ylim(self.y_max, self.y_min)

    def render_point(self, location, color="red"):
        """Draw a single point on the image."""
        self.axis.plot(
            [location[0]], [location[1]],
            marker="o",
            markersize=4,
            color=color
        )

    def render_rect(self, center, size, color="red"):
        """Draw a rectangle centered on a point."""
        x = center[0] - size[0] / 2
        y = center[1] - size[1] / 2
        rect = Rectangle(
            (x, y),
            size[0], size[1],
            edgecolor=color,
            facecolor='none',
            linewidth=2
        )
        self.axis.add_patch(rect)

    def render_text(self, position, text, color="white", outline="black"):
        """Render text with an outline."""
        self.axis.text(
            *position, text, size=12, color=color, ha='center', va='bottom',
            path_effects=[pe.withStroke(linewidth=2, foreground=outline)]
        )

    def update(self):
        """Update the canvas and display it."""
        self.canvas.draw()
