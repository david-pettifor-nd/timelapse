from timelapse import TimeLapse

tl = TimeLapse(
    images_directory='photos',
    save_directory='save',
    images_per_second=3
)

tl.make_video(with_graph=True, output_file='timelapse.mp4')