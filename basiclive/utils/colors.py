import numpy

RdYlGn = numpy.array([
    [0.64705882, 0., 0.14901961, 1.],
    [0.66243752, 0.01476355, 0.14932718, 1.],
    [0.68550557, 0.03690888, 0.14978854, 1.],
    [0.70088428, 0.05167243, 0.15009612, 1.],
    [0.72395233, 0.07381776, 0.15055748, 1.],
    [0.73933103, 0.08858131, 0.15086505, 1.],
    [0.76239908, 0.11072664, 0.15132641, 1.],
    [0.78546713, 0.13287197, 0.15178777, 1.],
    [0.80084583, 0.14763552, 0.15209535, 1.],
    [0.82391388, 0.16978085, 0.15255671, 1.],
    [0.83929258, 0.18454441, 0.15286428, 1.],
    [0.85428681, 0.21168781, 0.16370627, 1.],
    [0.86766628, 0.23983083, 0.17662438, 1.],
    [0.87658593, 0.25859285, 0.18523645, 1.],
    [0.8899654, 0.28673587, 0.19815456, 1.],
    [0.89888504, 0.30549789, 0.20676663, 1.],
    [0.91226451, 0.33364091, 0.21968474, 1.],
    [0.92118416, 0.35240292, 0.22829681, 1.],
    [0.93456363, 0.38054594, 0.24121492, 1.],
    [0.9479431, 0.40868897, 0.25413303, 1.],
    [0.95686275, 0.42745098, 0.2627451, 1.],
    [0.96101499, 0.45743945, 0.27658593, 1.],
    [0.96378316, 0.47743176, 0.28581315, 1.],
    [0.96793541, 0.50742022, 0.29965398, 1.],
    [0.97208766, 0.53740869, 0.31349481, 1.],
    [0.97485582, 0.557401, 0.32272203, 1.],
    [0.97900807, 0.58738947, 0.33656286, 1.],
    [0.98177624, 0.60738178, 0.34579008, 1.],
    [0.98592849, 0.63737024, 0.35963091, 1.],
    [0.98869666, 0.65736255, 0.36885813, 1.],
    [0.99223376, 0.68619762, 0.38362168, 1.],
    [0.99269512, 0.70926567, 0.40299885, 1.],
    [0.99300269, 0.72464437, 0.41591696, 1.],
    [0.99346405, 0.74771242, 0.43529412, 1.],
    [0.99377163, 0.76309112, 0.44821223, 1.],
    [0.99423299, 0.78615917, 0.46758939, 1.],
    [0.99469435, 0.80922722, 0.48696655, 1.],
    [0.99500192, 0.82460592, 0.49988466, 1.],
    [0.99546328, 0.84767397, 0.51926182, 1.],
    [0.99577086, 0.86305267, 0.53217993, 1.],
    [0.99623222, 0.88319877, 0.55309496, 1.],
    [0.99669358, 0.89750096, 0.57708574, 1.],
    [0.99700115, 0.90703576, 0.59307958, 1.],
    [0.99746251, 0.92133795, 0.61707036, 1.],
    [0.99777009, 0.93087274, 0.63306421, 1.],
    [0.99823145, 0.94517493, 0.65705498, 1.],
    [0.99853902, 0.95470973, 0.67304883, 1.],
    [0.99900038, 0.96901192, 0.6970396, 1.],
    [0.99946175, 0.98331411, 0.72103037, 1.],
    [0.99976932, 0.9928489, 0.73702422, 1.],
    [0.99123414, 0.99630911, 0.73702422, 1.],
    [0.97954633, 0.99138793, 0.72103037, 1.],
    [0.96201461, 0.98400615, 0.6970396, 1.],
    [0.94448289, 0.97662438, 0.67304883, 1.],
    [0.93279508, 0.97170319, 0.65705498, 1.],
    [0.91526336, 0.96432141, 0.63306421, 1.],
    [0.90357555, 0.95940023, 0.61707036, 1.],
    [0.88604383, 0.95201845, 0.59307958, 1.],
    [0.87435602, 0.94709727, 0.57708574, 1.],
    [0.8568243, 0.93971549, 0.55309496, 1.],
    [0.83529412, 0.93048827, 0.5349481, 1.],
    [0.81960784, 0.92372165, 0.52479815, 1.],
    [0.79607843, 0.9135717, 0.50957324, 1.],
    [0.78039216, 0.90680507, 0.4994233, 1.],
    [0.75686275, 0.89665513, 0.48419839, 1.],
    [0.73333333, 0.88650519, 0.46897347, 1.],
    [0.71764706, 0.87973856, 0.45882353, 1.],
    [0.69411765, 0.86958862, 0.44359862, 1.],
    [0.67843137, 0.86282199, 0.43344867, 1.],
    [0.65490196, 0.85267205, 0.41822376, 1.],
    [0.62637447, 0.8402153, 0.412995, 1.],
    [0.60668973, 0.83160323, 0.41084198, 1.],
    [0.57716263, 0.81868512, 0.40761246, 1.],
    [0.55747789, 0.81007305, 0.40545944, 1.],
    [0.52795079, 0.79715494, 0.40222991, 1.],
    [0.50826605, 0.78854287, 0.40007689, 1.],
    [0.47873895, 0.77562476, 0.39684737, 1.],
    [0.44921184, 0.76270665, 0.39361784, 1.],
    [0.4295271, 0.75409458, 0.39146482, 1.],
    [0.4, 0.74117647, 0.38823529, 1.],
    [0.37662438, 0.72979623, 0.38239139, 1.],
    [0.34156094, 0.71272587, 0.37362553, 1.],
    [0.3064975, 0.69565552, 0.36485967, 1.],
    [0.28312188, 0.68427528, 0.35901576, 1.],
    [0.24805844, 0.66720492, 0.3502499, 1.],
    [0.22468281, 0.65582468, 0.344406, 1.],
    [0.18961938, 0.63875433, 0.33564014, 1.],
    [0.16624375, 0.62737409, 0.32979623, 1.],
    [0.13118032, 0.61030373, 0.32103037, 1.],
    [0.09996155, 0.59238754, 0.31180315, 1.],
    [0.09196463, 0.57762399, 0.3041138, 1.],
    [0.07996924, 0.55547866, 0.29257978, 1.],
    [0.07197232, 0.54071511, 0.28489043, 1.],
    [0.05997693, 0.51856978, 0.2733564, 1.],
    [0.04798155, 0.49642445, 0.26182238, 1.],
    [0.03998462, 0.4816609, 0.25413303, 1.],
    [0.02798923, 0.45951557, 0.242599, 1.],
    [0.01999231, 0.44475202, 0.23490965, 1.],
    [0.00799692, 0.42260669, 0.22337562, 1.],
    [0., 0.40784314, 0.21568627, 1.]
])


def colormap(value, palette=RdYlGn):
    index = min(99, max(0, round(value*100)))
    rgba = (palette[index]*256).astype(int)
    rgba[-1] = palette[index][-1]
    return rgba


