-- Crea la base si no existe y fija charset/collation
CREATE DATABASE IF NOT EXISTS evalutia
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE evalutia;

-- Recomendación general
SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
