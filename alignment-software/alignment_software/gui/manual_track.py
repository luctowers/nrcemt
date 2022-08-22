"""Manual particle tracking step module."""


import os
import tkinter as tk
from tkinter import ttk
from tkinter.messagebox import showerror
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from .common import NumericSpinbox
from alignment_software.engine.csv_io import (
    write_marker_csv
)


MAX_PARTICLES = 13
BUTTON_WIDTH = 3
RADIO_PADDING = 5


class ManualTrackStep:
    """Step that handles manual particle tracking."""

    def __init__(
        self, main_window, loading_step, coarse_align_step, particle_positions
    ):
        """
        Create manual tracking step.
        Depends on loading step to get the output path.
        Depends on coarse alignment to load coarse aligned images.
        Depends on particle positions for shared particle data.
        """
        self.main_window = main_window
        self.loading_step = loading_step
        self.coarse_align_step = coarse_align_step
        self.manual_track_window = None
        self.particle_positions = particle_positions
        self.selected_particle = None

    def open(self, close_callback):
        """Opens the step and calls close_callback when done."""

        self.selected_particle = 0
        self.particle_positions.resize(MAX_PARTICLES, self.image_count())

        self.manual_track_window = ManualTrackWindow(
            self.main_window, MAX_PARTICLES,
            self.select_particle, self.interpolate, self.move,
            self.delete, self.reset
        )
        self.render_graphs()

        # cleanup
        def close():
            self.save()
            self.manual_track_window.destroy()
            self.manual_track_window = None
            close_callback(reset=True)
        self.manual_track_window.protocol("WM_DELETE_WINDOW", close)

    def save(self):
        """Save marker data to csv."""
        marker_csv = os.path.join(
            self.loading_step.get_output_path(),
            "marker_data.csv"
        )
        write_marker_csv(marker_csv, self.particle_positions.array)

    def load_image(self, i):
        """Load image from coarse align step."""
        return self.coarse_align_step.load_image(i)

    def image_count(self):
        """Returns the number of frames in the sequence."""
        return self.coarse_align_step.image_count()

    def select_image(self, i):
        """
        Renders coarse aligned images, along with markers and graphs.
        """
        image = self.load_image(i)
        self.main_window.image_frame.render_image(image)
        self.render_markers()
        self.main_window.image_frame.update()
        if self.manual_track_window is not None:
            self.manual_track_window.adjustment.update_particle_status(
                self.particle_positions
            )
            self.render_graphs()

    def select_particle(self, p):
        """Called when selected particle is updated."""
        self.selected_particle = p
        self.select_image(self.main_window.selected_image())

    def render_markers(self):
        """Renders dots on the image in particle locations."""
        i = self.main_window.selected_image()
        for p in range(self.particle_positions.particle_count()):
            particle_position = self.particle_positions.get_position(p, i)
            if particle_position is not None:
                if self.selected_particle == p:
                    color = "#FFC107"
                else:
                    color = "#03a9f4"
                self.main_window.image_frame.render_point(
                    particle_position, color
                )
                self.main_window.image_frame.render_text(
                    particle_position, p+1
                )

    def render_graphs(self):
        """Render the both x and y position graphs."""
        i = self.main_window.selected_image()
        p = self.selected_particle
        self.manual_track_window.x_position.render(
            self.particle_positions[p, :, 0], i
        )
        self.manual_track_window.y_position.render(
            self.particle_positions[p, :, 1], i
        )

    def canvas_click(self, x, y):
        """Handle click on the image, and update the particle position."""
        i = self.main_window.selected_image()
        p = self.selected_particle
        self.particle_positions[p, i] = (x, y)
        self.select_image(i)

    def move(self, x, y):
        """Called when directional controls are used."""
        i = self.main_window.selected_image()
        p = self.selected_particle
        position = self.particle_positions.get_previous_position(p, i)
        if position is None:
            showerror("Move error", "click the image to indicate a position")
        else:
            px, py = position
            self.particle_positions[p, i] = (px+x, py+y)
            self.select_image(i)

    def delete(self):
        """Deletes current selected particle position."""
        i = self.main_window.selected_image()
        p = self.selected_particle
        self.particle_positions.delete_position(p, i)
        self.select_image(i)

    def reset(self):
        """Resets all positions for selected particle."""
        i = self.main_window.selected_image()
        p = self.selected_particle
        self.particle_positions.reset(p)
        self.select_image(i)

    def interpolate(self, particle_index):
        """Interpolates positions on the selected particle."""
        success = self.particle_positions.attempt_interpolation(
            particle_index, "quadratic"
        )
        if not success:
            showerror("Interpolation error", "interpolation failed")
        else:
            self.select_image(self.main_window.selected_image())

    def focus(self):
        """Brings the optimization window to the top."""
        self.manual_track_window.lift()


class ManualTrackWindow(tk.Toplevel):
    """Manual tracking with directional controls and graphs."""

    def __init__(
        self, master, particle_count,
        select_command=None, interpolate_command=None, move_command=None,
        delete_command=None, reset_command=None
    ):
        """
        Creates the window.
        Accepts bunch commands to be called on user interactions.
        """
        super().__init__(master)
        self.geometry("500x600")
        self.minsize(500, 600)
        self.title("Manual Detection Window")

        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)

        # Adding widgets to window
        self.adjustment = ParticleAdjustmentFrame(
            self, particle_count,
            select_command, interpolate_command, move_command,
            delete_command, reset_command
        )
        self.adjustment.grid(row=0, column=0, sticky="nwse")
        self.y_position = PositionGraphFrame(self, "y position")
        self.y_position.grid(row=1, column=0, sticky="nwse")
        self.x_position = PositionGraphFrame(self, "x position")
        self.x_position.grid(row=2, column=0, sticky="nwse")


class PositionGraphFrame(tk.LabelFrame):
    """Single dimensional line graph with dots on points."""

    def __init__(self, master, text):
        """Creates the frame with a given text label."""
        super().__init__(master, text=text)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.figure = Figure(figsize=(100, 100), dpi=100)
        self.axis = self.figure.add_subplot()
        self.canvas = FigureCanvasTkAgg(self.figure, self)
        self.canvas.get_tk_widget().grid(column=0, row=0, sticky="nwse")

    def render(self, positions, selected_frame):
        """Renders sequence of positions, highlighted position."""
        self.axis.clear()
        self.axis.plot(
            positions, marker="o", markersize=2
        )
        self.axis.plot(
            selected_frame, positions[selected_frame],
            marker="o", markersize=5
        )
        self.axis.set_xlim(-1, len(positions))
        self.canvas.draw()


class ParticleAdjustmentFrame(tk.LabelFrame):
    """Frame with particle selector and directional controls."""

    def __init__(
        self, master, particle_count,
        select_command=None, interpolate_command=None, move_command=None,
        delete_command=None, reset_command=None
    ):
        """Create the frame."""
        super().__init__(master, text="Particle selection and adjustment")
        self.move_command = move_command

        selection_frame = tk.Frame(self)
        selection_frame.grid(row=0, column=0, sticky="we")
        self.selection_var = tk.IntVar(self, 0)
        if select_command is not None:
            self.selection_var.trace(
                'w', lambda a, b, c: select_command(self.selection_var.get())
            )
        self.status_vars = []
        for i in range(particle_count):
            radio = tk.Radiobutton(
                selection_frame, text=f"{i+1}",
                variable=self.selection_var, value=i
            )
            radio.grid(row=0, column=i)
            status_var = tk.StringVar(self, value="")
            status_label = ttk.Label(
                selection_frame, anchor="center", textvariable=status_var
            )
            status_label.grid(row=1, column=i, sticky="we")
            self.status_vars.append(status_var)

        control_frame = tk.Frame(self)
        control_frame.grid(row=1, column=0, sticky="we")

        self.step_entry = NumericSpinbox(control_frame, 5, (1, 100), width=5)
        self.step_entry.grid(row=1, column=1)

        # create all of the directional controls
        up_button = tk.Button(control_frame, text="▲", width=5)
        up_button.grid(row=0, column=1)
        up_button.config(command=lambda: self.move(0, -1))
        left_button = tk.Button(control_frame, text="◀", width=5)
        left_button.grid(row=1, column=0)
        left_button.config(command=lambda: self.move(-1, 0))
        down_button = tk.Button(control_frame, text="▼", width=5)
        down_button.grid(row=2, column=1)
        down_button.config(command=lambda: self.move(0, 1))
        right_button = tk.Button(control_frame, text="▶", width=5)
        right_button.grid(row=1, column=2)
        right_button.config(command=lambda: self.move(1, 0))
        up_left_button = tk.Button(control_frame, text="◤", width=5)
        up_left_button.grid(row=0, column=0)
        up_left_button.config(command=lambda: self.move(-1, -1))
        up_right_button = tk.Button(control_frame, text="◥", width=5)
        up_right_button.grid(row=0, column=2)
        up_right_button.config(command=lambda: self.move(1, -1))
        down_left_button = tk.Button(control_frame, text="◣", width=5)
        down_left_button.grid(row=2, column=0)
        down_left_button.config(command=lambda: self.move(-1, 1))
        down_right_button = tk.Button(control_frame, text="◢", width=5)
        down_right_button.grid(row=2, column=2)
        down_right_button.config(command=lambda: self.move(1, 1))

        self.interpolate_button = tk.Button(
            control_frame, text="Interpolate", width=10
        )
        self.interpolate_button.grid(row=0, column=3)
        if interpolate_command is not None:
            self.interpolate_button.config(
                command=lambda: interpolate_command(self.selection_var.get())
            )

        self.delete_button = tk.Button(
            control_frame, text="Delete", width=10
        )
        self.delete_button.grid(row=1, column=3)
        if delete_command is not None:
            self.delete_button.config(
                command=lambda: delete_command()
            )

        self.reset_button = tk.Button(
            control_frame, text="Reset", width=10
        )
        self.reset_button.grid(row=2, column=3)
        if reset_command is not None:
            self.reset_button.config(
                command=lambda: reset_command()
            )

    def update_particle_status(self, particle_positions):
        """Update particle status indicators."""
        for p in range(particle_positions.particle_count()):
            status = particle_positions.get_status(p)
            if status == "complete":
                icon = "●"
            elif status == "partial":
                icon = "◒"
            else:
                icon = "○"
            self.status_vars[p].set(icon)

    def move(self, x, y):
        """Call the move command when a directional input is pressed."""
        if self.move_command is not None:
            step = self.step_entry.get()
            self.move_command(x * step, y * step)
