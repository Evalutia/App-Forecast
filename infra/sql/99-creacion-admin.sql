USE evalutia;

INSERT INTO usuarios (correo, hash_password, rol)
VALUES ('admin@evalutia.com', '$2b$11$6WJXyYf7x0p00/Z2ituT6uXArHM83W1G7ojDUon4/b.Ma.URWyxAi', 'administrador');

INSERT INTO usuarios (correo, hash_password, rol)
VALUES ('rodrigo@ecologictech.com.uy', '$2b$11$F99tqmuD3GmMSI77FBGIWOH54Db79CWSwrbDc2SykvWyd4manzs3K', 'duenoDeEmpresa');
