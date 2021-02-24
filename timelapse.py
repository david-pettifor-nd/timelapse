"""
Author: David W Pettifor
GitHub: david-pettifor-nd
Email: dpettifo@nd.edu

TimeLapse - A Class of functions to take in a series of timelapse photographs,
rendering them sequentially as a video.

Supports temperature extraction from timestamps using OCR to draw temperature
points on a line graph, drawing a graph representing current and previous
temperature readings on each sequential frame.

Requires:
    - ffmpeg [https://ffmpeg.org/] (for video rendering)
    - tesseract [https://github.com/tesseract-ocr/tesseract](for OCR temperature extraction)
    - PIL [https://pillow.readthedocs.io/en/stable/] (for drawing graphs)

Usage:
    from timelapse import TimeLapse

    tl = TimeLapse(
        images_directory='/home/user/Pictures/timelapse',
        save_directory='/home/user/Pictures/timelapse/save'
    )

    tl.make_video(output_file='/home/user/Pictures/timelapse/myvideo.mp4')
"""
import os
import datetime
import copy
import shutil

# Used to process images against tesseract OCR
from multiprocessing import Pool
import pytesseract

# Used to draw graphs on each image (if enabled)
from PIL import Image, ImageDraw, ImageFont

# --== Different ways to order files within the directory ==--
# Order based on the created timestamp of the file
ORDER_CREATED = os.path.getctime

# Order based ono the modified timestamp of the file
ORDER_MODIFIED = os.path.getmtime

# Order based on the file name (useful for sequential images, such as timelapse)
ORDER_NAME = None

def parse_temperature_text(input_text):
    """
    Default function to parse temperature out of the returned OCR text.
    You should write your own parser function to do this.  Be sure it
    accepts a string and returns a string!
    """
    # I know there are two temperature readings, the first Celsius
    # and the second Farenheit...
    degrees = input_text.split('°')
    # so i'll return the second (degrees[1]) but trim the space
    return degrees[1].split(' ')[1]

class TimeLapse():
    """
    A collection of steps which produces a timelapse video (using `ffmpeg`) from a series
    of still images, supporting temperature data extraction using Tesseract OCR from the 
    footer timestamp on each image, drawing a progressive graph, then compling into
    a video file.
    """

    def __init__(self, **kwargs):
        # Rendered video (Images Per Second: how many images per second of video)
        # Note: the higher this number is, the smoother (but shorter) the video will be
        self.images_per_second = 15

        # Framerate should be AT LEAST the Images per second, otherwise you'll start loosing images
        # (Note: the higher this number, the larger the file size.  25 is a pretty smooth value)
        self.framerate = 25

        # Binding box for OCR to extract temperature out of.  
        # May need to tweak and test for your cases...OCR can be kinda finicky
        # Format is (top-left-x, top-left-y, bottom-right-x, bottom-right-y)
        self.ocr_binding_box = (0, 3174, 4412, 3308)

        # will will always need some sort of text parser to clean up what tesseract OCR
        # returns back, so make this something the end user can modify
        self.temperature_text_parser = parse_temperature_text

        # How many threads should we spawn (up to)?  This will depend on each system,
        # but if left "None", it will use what your OS returns back as the CPU count
        self.process_threads = None

        # Where is the directory with all of the files?
        self.images_directory = None

        # What directory should we save temporary images in?
        self.save_directory = None

        # --= Temperature Graph Details Below
        # Note: Colors can be english names, or RGBA values
        self.grid_color = (255, 255, 255, 150)
        self.graph_bg_color = (0, 0, 0, 200)
        self.graph_border_color = 'white'
        self.line_color = 'white'
        self.tick_color = 'white'
        self.freezing_line_color = (29, 214, 255, 255)
        # a safe font that's on most systems:
        # Note: PIL will search your OS's default font locations.  
        #   You may also set this to a specific font file.
        self.graph_label_font = 'Courier New'

        # Dimensions of the graph
        self.graph_height = 650
        self.graph_width = 4086
        self.padding = 60

        # Margins - how far from the edge of the image should the graph be drawn
        self.graph_height_margin = 75
        self.graph_width_margin = 190

        # Y-Axis ticker (drawn at every 10 degrees between min and max values)
        self.ticker_width = 20

        # None if you want just a smooth line, otherwise value will be in pixels
        self.plot_point_size = None
        self.plot_point_color = 'white'
        self.plot_point_outline = 'black'

        # --== END OF VARIRABLES: DO NOT MODIFY BELOW THIS LINE ==-- #

        # What file types should be supported -- loose check based on filename
        self.valid_file_extensions = [
            '.png',
            '.jpg',
            '.jpeg'
        ]

        # default ordering as file name
        # this can be changed after init though, before processing
        self.order = ORDER_NAME

        # COMPUTED VALUES:
        self.deg_min = None
        self.deg_max = None
        self.pixels_per_degree = 1
        self.total_frames = 1
        self.image_series = []

        # now that we have our defaults set, update any that are passed in
        self.__dict__.update(kwargs)

    # --== BEGIN GRAPH DRAWING FUNCTIONS ==-- 
    def compute_pixels_per_temp(self):
        """
        Assumes deg_max and deg_min have been appropriately set.
        Figures how how many pixels on the Y-axis each "degree" represents.
        """
        # figure out how many degrees we have to show (range)
        temp_range = float(self.deg_max) - float(self.deg_min)

        # compute the height of the y-axis
        y_axis_height = float(self.graph_height - (self.padding * 2))

        # simple division!
        return y_axis_height / temp_range

    def get_temp_y_point(self, temp):
        """
        computes temperature times pixels and adds the graph hight and padding
        """
        y_axis = self.graph_height_margin + self.graph_height - self.padding - ((temp - self.deg_min) * self.pixels_per_degree)
        return y_axis

    def get_x_point(self, index):
        """
        computes where on the x-axis this point should go
        index should be zero-based
        """
        x_axis_length = self.graph_width - (self.padding * 2)

        # pixels per frame
        pixels_per_frame = float(x_axis_length) / float(len(self.image_series) - 1)
        x_axis = self.graph_width_margin + self.padding + (pixels_per_frame * index)
        return x_axis

    def draw_graph_borders(self, image):
        """
        Draws the box of the graph, with a border
        """
        img = ImageDraw.Draw(image, 'RGBA')
        img.rectangle([self.graph_width_margin, self.graph_height_margin, self.graph_width_margin + self.graph_width, self.graph_height_margin + self.graph_height], fill=self.graph_bg_color, outline=self.graph_border_color)
        return image

    def draw_grid(self, image):
        """
        Draws:
            - the Y-axis and X-axis across the graph
            - Y-axis tick marks at every 10 degrees between the min and max temperatures
            - the 32 degree freezing line (if its between the min and max temperatures)
            - adds the min/max temp values as labels
        """
        img = ImageDraw.Draw(image, 'RGBA')
        img.line([(self.graph_width_margin + self.padding), (self.graph_height_margin + self.graph_height - self.padding), (self.graph_width_margin + self.padding), (self.graph_height_margin + self.padding)], fill=self.grid_color, width=2)
        img.line([(self.graph_width_margin + self.padding), (self.graph_height_margin + self.graph_height - self.padding), (self.graph_width_margin + self.graph_width - self.padding),(self.graph_height_margin + self.graph_height - self.padding)], fill=self.grid_color, width=2)

        # draw every 10 degrees mark
        current_deg = self.deg_min
        while current_deg <= self.deg_max:
            if current_deg % 10 == 0:
                # draw this line
                y_axis_point = self.get_temp_y_point(current_deg)
                img.line([(self.graph_width_margin + self.padding - (self.ticker_width / 2)), y_axis_point, (self.graph_width_margin + self.padding + (self.ticker_width / 2)), y_axis_point], fill=self.tick_color, width=2)

            current_deg += 1
        
        # draw the 32 degrees line
        if self.deg_min <= 32 <= self.deg_max:
            freezing_line = self.get_temp_y_point(32)
            img.line([(self.graph_width_margin + self.padding), freezing_line, (self.graph_width_margin + self.graph_width - self.padding), freezing_line], fill=self.freezing_line_color, width=1)

        # add min/max temp labels
        fnt = ImageFont.truetype(font=self.graph_label_font, size=40)
        img.text(((self.graph_width_margin + 20), (self.graph_height_margin + self.graph_height - (self.padding / 2) - 20)), str(self.deg_min) + '°', font=fnt, fill=self.grid_color)
        img.text(((self.graph_width_margin + 20), (self.graph_height_margin + (self.padding / 2) - 20)), str(self.deg_max) + '°', font=fnt, fill=self.grid_color)

        return image

    def add_temps(self, image, temperature_points):
        """
        Loops through each of the previous temperatures and draws them on the current image.
        Also draws a connecting line between each of them.
        Note: If PLOT_POIONT_SIZE is `None`, the points will not be drawn, and only the line will be drawn.
        """
        img = ImageDraw.Draw(image['image'], 'RGBA')
        last_point = None
        for index, point in enumerate(temperature_points, start=0):
            y = self.get_temp_y_point(point)
            x = self.get_x_point(index)
            if self.plot_point_size:
                img.ellipse((x - (self.plot_point_size / 2), y - (self.plot_point_size / 2), x + (self.plot_point_size / 2), y + (self.plot_point_size / 2)), fill=self.plot_point_color, outline=self.plot_point_outline)

            if last_point:
                # draw a line between the last point and this point
                img.line([last_point['x'], last_point['y'], x, y], fill="white", width=2)
            last_point = {
                'x': x,
                'y': y
            }
        return image['image']

    def draw_graph(self, image):
        """
        For the passed in image, draw the graph box, grid, and all temperature points.
        """
        image['image'] = self.draw_graph_borders(image['image'])
        image['image'] = self.draw_grid(image['image'])
        image['image'] = self.add_temps(image, image['temps'])

        return image

    # --== END GRAPH DRAWING FUNCTIONS ==--
    
    def load_images(self):
        """
        Loads up the images from the directory set and loads any image
        that ends with the valid file extensions.
        It also loads an ordering value and sorts them based on the method
        chosen (defaults to filename).

        These are stored in `self.image_series`.
        """
        file_list = []
        for filename in os.listdir(self.images_directory):
            if filename.lower().endswith(tuple(self.valid_file_extensions)):
                # how do we want to order these?
                order_value = filename
                if self.order:
                    # assume this is a callable function
                    order_value = self.order(os.path.join(self.images_directory, filename))
                file_list.append({
                    'file_name': filename,
                    'order': order_value
                })
        self.image_series = sorted(file_list, key=lambda item: item['order'])

        # set the index for each image (needed later)
        for index, img in enumerate(self.image_series, start=1):
            img['index'] = index

        print("Loaded", len(self.image_series), "files")

    def process_image(self, file_meta):
        """
        A single image to process using OCR to extract temperature data from.
        """
        # crop to the bottom timestamp
        im = Image.open(os.path.join(self.images_directory, file_meta['file_name']))
        timestamp_border = im.crop(self.ocr_binding_box)
        text = pytesseract.image_to_string(timestamp_border)

        # try to parse out the temperature from the returned text
        # if this fails, it will show the image to the user and ask
        # for the temperature value
        try:
            # extract text and convert to an integer
            temp = int(self.temperature_text_parser)
            return {
                'image': im,
                'file_name': file_meta['file_name'],
                'temp': temp,
                'order': file_meta['order'],
                'index': file_meta['index']
            }

        # if we can't extract the text or it doesn't convert to an integer properly...
        # just ask the user what the temp is
        except (IndexError, ValueError):
            print("!! Failed to extract temperature.")
            im.show()
            temp = int(input("Enter temperature seen in image:"))
            
            return {
                'image': im,
                'file_name': file_meta['file_name'],
                'temp': temp,
                'order': file_meta['order'],
                'index': file_meta['index']
            }


    def process_images(self):
        """
        Runs through each image and uses Tesseract OCR to extrac the temperature
        out of them, then stores each image, paired with its determined temp
        into "self.image_series".
        """
        print("Beginning processing of images...")
        processing_start = datetime.datetime.now()
        current_temps = []

        # create a pool to thread the OCR processing of images (loads faster)
        with Pool(self.process_threads) as p:
            self.image_series = p.map(self.process_image, self.image_series)
        
        
        # compute min and max temps, as well as compound temperatures into each image object
        for img in self.image_series:
            if self.deg_max is None or img['temp'] > self.deg_max:
                self.deg_max = img['temp']
            if self.deg_min is None or img['temp'] < self.deg_min:
                self.deg_min = img['temp']
            
            current_temps.append(img['temp'])
            img['temps'] = copy.deepcopy(current_temps)

        self.pixels_per_degree = self.compute_pixels_per_temp()
        self.total_frames = len(self.image_series)

        processing_end = datetime.datetime.now()
        print("\t...completed [ in", (processing_end - processing_start), "]")
        print("Determined temperature ranges:")
        print("\t>> Max Temp:", self.deg_max)
        print("\t>> Min Temp:", self.deg_min)
    
    def render_images(self, add_graph=True):
        """
        Loops through each image and copies them to the save directory.
        If "add_graph" is True (default), it will draw the temperature graph
        on each image as it is copied over.
        """
        # how many digits of leading zeros will be possibly need?
        max_digits = len(str(len(self.image_series)))
        if add_graph:
            print("Generating graphs on all frames...")
            # Special note from the developer: you may be asking, why not thread this?
            # Because of the overhead of moving PIL Image files into their own processes
            # back and forth, I found the overhead to be monsterously expensive, and thus
            # faster (by orders in the 10s) to simply loop through them.
            for img in self.image_series:
                image_obj = self.draw_graph(img)
                # composite the file name (based on index/order)
                new_filename = 'TIMELAPSE' + format(image_obj['index'], '0'+str(max_digits)) + '.JPG'
                image_obj['image'].save(os.path.join(self.save_directory, new_filename))
        else:
            # just copy it over then
            for index, image_obj in enumerate(self.image_series, start=1):
                new_filename = 'TIMELAPSE' + format(index, '0'+str(max_digits)) + '.JPG'
                shutil.copyfile(os.path.join(self.images_directory, image_obj['file_name']), os.path.join(self.save_directory, new_filename))

    def render_video(self, save_as='timelapse.mp4'):
        """
        Calls `ffmpeg` with the framerate and IPS variables to render the image based
        on the files within the "save" directory.
        """
        print("Calling ffmpeg...")
        os.system("cd " + self.save_directory + " && ffmpeg -f image2 -framerate "+str(self.framerate)+" -pattern_type sequence -start_number 1 -r "+str(self.images_per_second)+" -i TIMELAPSE%0"+str(len(str(len(self.image_series))))+"d.JPG "+save_as)
        print("Done.")

    def make_video(self, with_graph=True, output_file='timelapse.mp4'):
        """
        Calls all appropriate functions to take what's in the images directory
        and makes a video saved at the "output_file" location.
        """
        # first load all images
        self.load_images()

        # if we are making it with the graph, we have to process each image
        if with_graph:
            self.process_images()
        
        # then render (or just copy) the images
        self.render_images(add_graph=with_graph)

        # finally, render the video
        self.render_video(save_as=output_file)
