# TimeLapse
A Python class that renders timelapse video from sequential photographs.

## Requirements
There are two external programs that you must have installed on your system in order to fully support this library:
* [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)
    * And the Python wrapper for it: [pytesseract](https://github.com/madmaze/pytesseract)
* [ffmpeg](https://ffmpeg.org/) (called through an `os.system()` call)

## Basic Usage

The most basic usage to render a video (with a graph showing temperature changes on each frame):
```python
from timelapse import TimeLapse

tl = TimeLapse(
    images_directory='/home/user/Pictures/timelapse/',
    save_directory='/home/user/Pictures/timelapse/save/'
)

tl.make_video(with_graph=False, output_file='/home/user/Pictures/timelapse/save/timelapse.mp4')
```

## Temperature Trends

Included is support for [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) to extract temperature information often found in the footer (or some timestamp area) on trailcam footage (see examples).  This graph can be drawn by settings `with_graph=True`.

#### Setting OCR Binding Box
Finding the temperature through OCR may take some trial and error, but can be done by adjusting to fit your specific temperature binding box on the image:
```python
from timelapse import TimeLapse

tl = TimeLapse(
    images_directory='/home/user/Pictures/timelapse/',
    save_directory='/home/user/Pictures/timelapse/save/'
)

# all coordinates are assuming top-left corner of image is (0,0)
# note: this can also be passed into the TimeLapse constructor
tl.ocr_binding_box=(
    0,      # top-left corner X-value
    3174,   # top-left corner Y-value
    4412,   # bottom-right corner X-value
    3308    # bottom-right corner Y-value
)

tl.make_video(with_graph=True, output_file='/home/user/Pictures/timelapse/save/timelapse.mp4')
```
This will analyze each photograph individually to extract the temperature value from it.  

#### Creating Custom Temperature Text Parser
By default, the temperature text parser built-in is designed for my specific trailcam footer, which has two temperature readings (the first in Celsius, the second in Farenheit).  You will likely need to adjust this by defining your own parsing function, and setting it accordingly:
```python
from timelapse import TimeLapse

def custom_parser(input_text):
    # remove the degree symbol (°) and any whitespace
    return input_text.replace('°', '').strip()

tl = TimeLapse(
    images_directory='/home/user/Pictures/timelapse/',
    save_directory='/home/user/Pictures/timelapse/save/'
)

# set the temperature parser function
tl.temperature_text_parser = custom_parser

tl.make_video(with_graph=True, output_file='/home/user/Pictures/timelapse/save/timelapse.mp4')
```

## Options

#### Graph Rendering Options

All options below can be passed in to the `TimeLapse` constructor as parameters, or set after construction.
Options below are shown with their default values.
```python
# -- All colors can be plain English names, or RGBA values as tuples --

# color of the grid lines
grid_color = (255, 255, 255, 150)

# background fill of the graph
graph_bg_color = (0, 0, 0, 200)

# color of the graph border
graph_border_color = 'white'

# color of the line drawn between temperature points
line_color = 'white'

# ticks are drawn on the Y-axis at every 10 degrees; this is their color:
tick_color = 'white'
# and width
ticker_width = 20

# draw a line at the 32 degree mark (sorry Celsius), this is the color for that line:
freezing_line_color = (29, 214, 255, 255)

# a safe font that's on most systems (used to label the min and max temperatures on the Y-axis):
# Note: PIL will search your OS's default font locations.  
#   You may also set this to a specific font file.
graph_label_font = 'Courier New'

# Dimensions of the graph
graph_height = 650
graph_width = 4086

# padding is the space between the edge of the graph and where the X and Y axis are drawn
padding = 60

# Margins - how far from the edge of the image should the graph be drawn
# note: ideally the width (specified above) should be equal to the width of the image minus 2 x the margin (so it's centered evenly)
graph_height_margin = 75
graph_width_margin = 190

# Plot points can be drawn to represent each temperature value.
# `None` if you want just a smooth line, otherwise value will be in pixels
plot_point_size = None
plot_point_color = 'white'
plot_point_outline = 'black'
```

#### Input File Options

```python
# What file types should be supported -- loose check based on filename (should all be lowercase)
valid_file_extensions = [
    '.png',
    '.jpg',
    '.jpeg'
]

# If we want to search recursively in all sub-folders, set this to True
# (Useful when your trailcam has to stack images into sub-directories)
# Note: if this is enabled, it is strongly encouraged to set the ordering
# to either ORDER_CREATED or ORDER_MODIFIED as name conflicts may be likely
recursive_search = False
```

Sequential ordering can be determined using three different methods:
* Created Timestamp: uses `os.path.getctime()` to determine the timestamp of when the file was created
* Modified Timestamp: uses `os.path.getmtime()` to determine the timestamp of when the file was last modified
* File Name: simply order based on the alphabetical ordering of the file name itself.

```python
from timelapse import ORDER_CREATED, ORDER_MODIFIED, ORDER_NAME

# default ordering as file name.  most timelapse cameras will save their images in this way,
# but may resort to sub-directory stacking, creating duplicate filenames when looking at the entire
# dataset.  In this case, it would be good to use ORDER_CREATED or ORDER_MODIFIED.
order = ORDER_NAME
```

#### Video Rendering Options

```python
# Rendered video (Images Per Second: how many images per second of video)
# Note: the higher this number is, the smoother (but shorter) the video will be
images_per_second = 15

# Framerate should be AT LEAST the Images per second, otherwise you'll start loosing images
# (Note: the higher this number, the larger the file size.  25 is a pretty smooth value)
framerate = 25
```

#### Multithreading Option
Multithreading is used when extracting temperature values from images and when drawing graphs on individual image frames.  By default, the script will create a number of processes that matches the number of cores of your system (recommended).
But you _can_ adjust this with:

```python
# How many threads should we spawn (up to)?  This will depend on each system,
# but if left "None", it will use what your OS returns back as the CPU count
process_threads = None
```

## Examples

If I wanted to use all of the jpg images desktop to render two videos, one with a graph and one without, with a slow rate of 2 images per second, and order them based on their created date:
```python
from timelapse import TimeLapse, ORDER_CREATED

tl = TimeLapse(
    images_directory='/home/user/Desktop/',
    save_directory='/home/user/Desktop/save/',
    valid_file_extensions=['.jpg'],
    images_per_second=2,
    order=ORDER_CREATED
)

tl.make_video(with_graph=True, output_file='/home/user/Desktop/timelapse_with_graph.mp4')
tl.make_video(with_graph=False, output_file='/home/user/Desktop/timelapse_without_graph.mp4')
```