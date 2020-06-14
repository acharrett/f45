CREATE TABLE `f45_workouts` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `date_time` datetime DEFAULT NULL,
  `day_of_week` text DEFAULT NULL,
  `calories` int(11) DEFAULT NULL,
  `points` float DEFAULT NULL,
  `workout_name` varchar(50) DEFAULT NULL,
  `elapsed_seconds` int(11) DEFAULT NULL,
  `average_heartrate` int(11) DEFAULT NULL,
  `weight_band` varchar(5) DEFAULT NULL,
  `image_url` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`);

