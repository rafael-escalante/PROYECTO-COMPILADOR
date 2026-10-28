import re
import tkinter as tk
from tkinter import ttk

# datos del lenguaje
TIPOS = ["ENTER", "REALER", "CADER"]
PALABRAS_RESERVADAS = TIPOS + ["void", "while", "endwhile", "return"]

REGEX_NOMBRE = r"re[A-Z][a-z]+"

OPERADORES = ["+", "-", "*", "/"]
RELACIONALES = [">", "<", ">=", "<=", "==", "!="]
SIMBOLOS = ["(", ")", ",", ";", ":", "=", "--", "++", "{", "}"] + OPERADORES + RELACIONALES

OPERADORES_PERMITIDOS = {
    "ENTER": ["+", "-", "*"],
    "REALER": ["+", "-", "*", "/"],
    "CADER": ["+", "-"],
}

PATRON_TOKENS = r'[“"][^”"]*[”"]|\d+\.\d+|\d+|[^\W\d]\w*|-\s*-|\+\+|[<>=!]=|[+\-*/(),;:<>={}]|\S'

# tablas
tabla_simbolos = []
tabla_errores = []
errores_pendientes = []
variables = {}
funciones = {}
funcion_actual = {}


def agregar_error(lexema, renglon, descripcion):
    errores_pendientes.append((renglon, lexema, descripcion))


# funciones para identificar lexemas
def es_entero(t):
    return re.fullmatch(r"\d+", t) is not None


def es_real(t):
    return re.fullmatch(r"\d+\.\d+", t) is not None


def es_cadena(t):
    return re.fullmatch(r'[“"][^”"]*[”"]', t) is not None


def es_palabra(t):
    return re.fullmatch(r"[^\W\d]\w*", t) is not None and t not in PALABRAS_RESERVADAS


def es_operando(t):
    return es_palabra(t) or es_entero(t) or es_real(t) or es_cadena(t)


def es_conocido(t):
    return t in PALABRAS_RESERVADAS or t in SIMBOLOS or es_operando(t)


def buscar_variable(nombre):
    if funcion_actual and nombre in funcion_actual["locales"]:
        return funcion_actual["locales"][nombre]
    return variables.get(nombre)


def ambito_actual():
    if funcion_actual:
        return funcion_actual["locales"]
    return variables


def tipo_de(t):
    if t in TIPOS:
        return t
    if es_cadena(t):
        return "CADER"
    if es_real(t):
        return "REALER"
    if es_entero(t):
        return "ENTER"
    tipo = buscar_variable(t)
    if tipo is None:
        return ""
    return tipo


def es_compatible(esperado, recibido):
    # REALER acepta valores ENTER, pero ENTER NO acepta REALER
    if esperado == recibido:
        return True
    return esperado == "REALER" and recibido == "ENTER"


def agregar_simbolos(tokens, tipo_declaracion=""):
    for t in tokens:
        if es_palabra(t):
            if re.fullmatch(REGEX_NOMBRE, t) is None:
                tipo = ""
            elif tipo_declaracion != "":
                tipo = tipo_declaracion
            elif buscar_variable(t) is not None:
                tipo = buscar_variable(t)
            elif t in funciones:
                tipo = funciones[t][0]
            else:
                tipo = ""
        elif es_entero(t) or es_real(t) or es_cadena(t):
            tipo = tipo_de(t)
        else:
            tipo = ""

        if (t, tipo) not in tabla_simbolos:
            tabla_simbolos.append((t, tipo))


def quitar_punto_y_coma(tokens):
    if tokens[-1] == ";":
        return tokens[:-1]
    return tokens


def argumentos_bien_escritos(argumentos):
    if argumentos == []:
        return True
    if len(argumentos) % 2 == 0:
        return False
    for i in range(len(argumentos)):
        if i % 2 == 0 and not es_operando(argumentos[i]):
            return False
        if i % 2 == 1 and argumentos[i] != ",":
            return False
    return True


def leer_expresion(partes):
    elementos = []
    i = 0
    espero_operando = True
    while i < len(partes):
        t = partes[i]
        if espero_operando:
            if es_palabra(t) and i + 1 < len(partes) and partes[i + 1] == "(":
                if ")" not in partes[i + 2:]:
                    return None
                j = partes.index(")", i + 2)
                argumentos = partes[i + 2:j]
                if not argumentos_bien_escritos(argumentos):
                    return None
                elementos.append(("llamada", t, argumentos[::2]))
                i = j + 1
            elif es_operando(t):
                elementos.append(t)
                i = i + 1
            else:
                return None
            espero_operando = False
        else:
            if t in OPERADORES:
                espero_operando = True
            elif not (t in ["--", "++"] and i == len(partes) - 1):
                return None
            elementos.append(t)
            i = i + 1
    if espero_operando:
        return None
    return elementos


def leer_parametros(partes):
    if partes == []:
        return []
    parametros = []
    pedazo = []
    for t in partes + [","]:
        if t == ",":
            if len(pedazo) != 2 or pedazo[0] not in TIPOS or not es_palabra(pedazo[1]):
                return None
            parametros.append((pedazo[0], pedazo[1]))
            pedazo = []
        else:
            pedazo.append(t)
    return parametros


def revisar_indefinidas(elementos, renglon):
    hubo_error = False
    ya_reportadas = []
    for e in elementos:
        if isinstance(e, tuple):
            nombre = e[1]
            if nombre not in funciones and nombre not in ya_reportadas:
                agregar_error(nombre, renglon, "Función indefinida")
                ya_reportadas.append(nombre)
                hubo_error = True
            lexemas = e[2]
        else:
            lexemas = [e]
        for t in lexemas:
            if es_palabra(t) and buscar_variable(t) is None and t not in ya_reportadas:
                agregar_error(t, renglon, "Variable indefinida")
                ya_reportadas.append(t)
                hubo_error = True
    return hubo_error


def revisar_argumentos(llamada, renglon):
    tipos_parametros = funciones[llamada[1]][1]
    argumentos = llamada[2]
    for i in range(min(len(argumentos), len(tipos_parametros))):
        if not es_compatible(tipos_parametros[i], tipo_de(argumentos[i])):
            agregar_error(argumentos[i], renglon, "Incompatibilidad de tipos, " + tipos_parametros[i])


def revisar_tipos(elementos, tipo, renglon):
    for e in elementos:
        if isinstance(e, tuple):
            nombre = e[1]
            if not es_compatible(tipo, funciones[nombre][0]):
                agregar_error(nombre, renglon, "Incompatibilidad de tipos, " + tipo)
            revisar_argumentos(e, renglon)
        elif e in OPERADORES or e in ["--", "++"]:
            if e[0] not in OPERADORES_PERMITIDOS[tipo]:
                agregar_error(e, renglon, "Incompatibilidad de tipos, " + tipo)
        elif not es_compatible(tipo, tipo_de(e)):
            agregar_error(e, renglon, "Incompatibilidad de tipos, " + tipo)


# revision de instrucciones
def revisar_declaracion(tokens, renglon):
    tipo = tokens[0]
    cuerpo = quitar_punto_y_coma(tokens)
    medio = cuerpo[1:]

    if len(medio) == 0:
        return

    # NUEVA FUNCIONALIDAD: Permitir declaraciones con asignación en la misma línea (ej. ENTER reA = 5;)
    if len(medio) >= 3 and medio[1] == "=":
        nombre = medio[0]
        ambito = ambito_actual()
        
        # 1. Registrar la variable en el entorno local
        if re.fullmatch(REGEX_NOMBRE, nombre) is None:
            agregar_error(nombre, renglon, "Variable indefinida")
        elif nombre in ambito:
            agregar_error(nombre, renglon, "Declaración duplicada")
        else:
            ambito[nombre] = tipo

        # 2. Delegar la verificación de la asignación a su respectiva función
        tokens_asignacion = tokens[1:] # Pasamos a partir de la variable, ignorando el tipo
        revisar_asignacion(tokens_asignacion, renglon)
        
        agregar_simbolos(tokens, tipo)
        return

    # Comprobación de declaración clásica (ej. ENTER reA, reB;)
    bien_escrita = (len(cuerpo) >= 2 and len(medio) % 2 == 1)
    if bien_escrita:
        for i in range(len(medio)):
            if i % 2 == 0 and not es_palabra(medio[i]):
                bien_escrita = False
            if i % 2 == 1 and medio[i] != ",":
                bien_escrita = False
    
    if not bien_escrita:
        return

    ambito = ambito_actual()
    for nombre in medio[::2]:
        if re.fullmatch(REGEX_NOMBRE, nombre) is None:
            agregar_error(nombre, renglon, "Variable indefinida")
        elif nombre in ambito:
            agregar_error(nombre, renglon, "Declaración duplicada")
        else:
            ambito[nombre] = tipo

    agregar_simbolos(tokens, tipo)


def revisar_asignacion(tokens, renglon):
    cuerpo = quitar_punto_y_coma(tokens)
    destino = cuerpo[0]
    if len(cuerpo) < 3 or cuerpo[1] != "=":
        return
    elementos = leer_expresion(cuerpo[2:])
    if elementos is None:
        return

    hay_indefinidas = revisar_indefinidas([destino] + elementos, renglon)
    if not hay_indefinidas:
        revisar_tipos(elementos, buscar_variable(destino), renglon)

    agregar_simbolos(tokens)


def revisar_while(tokens, renglon):
    cuerpo = quitar_punto_y_coma(tokens)
    
    # Detectamos si el usuario intenta declarar la variable dentro del while
    # Ej: while ( ENTER reContador < 5 ) -> Son 7 tokens
    tiene_declaracion = (len(cuerpo) == 7 and cuerpo[2] in TIPOS)
    
    bien_escrito = False
    
    if tiene_declaracion:
        # Estructura: while ( TIPO variable relacional operando )
        bien_escrito = (cuerpo[1] == "(" and cuerpo[6] == ")" and
                        es_palabra(cuerpo[3]) and 
                        (cuerpo[4] in RELACIONALES or cuerpo[4] == "=") and
                        es_operando(cuerpo[5]))
    else:
        # Estructura clásica: while ( variable relacional operando )
        bien_escrito = (len(cuerpo) == 6 and cuerpo[1] == "(" and cuerpo[5] == ")" and
                        es_operando(cuerpo[2]) and 
                        (cuerpo[3] in RELACIONALES or cuerpo[3] == "=") and
                        es_operando(cuerpo[4]))
                        
    if not bien_escrito:
        return

    # Extraemos los datos dependiendo de si se declaró ahí o no
    if tiene_declaracion:
        tipo_decl = cuerpo[2]
        izquierda = cuerpo[3]
        operador = cuerpo[4]
        derecha = cuerpo[5]
        
        # ¡NUEVO!: Registramos la variable para que exista en el ámbito de la función
        ambito = ambito_actual()
        if re.fullmatch(REGEX_NOMBRE, izquierda) is None:
            agregar_error(izquierda, renglon, "Variable indefinida")
        elif izquierda in ambito:
            agregar_error(izquierda, renglon, "Declaración duplicada")
        else:
            ambito[izquierda] = tipo_decl
    else:
        izquierda = cuerpo[2]
        operador = cuerpo[3]
        derecha = cuerpo[4]


    # Revisiones semánticas de compatibilidad de tipos
    elementos_a_revisar = [derecha] if tiene_declaracion else [izquierda, derecha]
    if not revisar_indefinidas(elementos_a_revisar, renglon):
        tipo_izq = tipo_de(izquierda)
        tipo_der = tipo_de(derecha)
        if tipo_izq != "" and tipo_der != "" and not es_compatible(tipo_izq, tipo_der):
            agregar_error(derecha, renglon, "Incompatibilidad de tipos, " + tipo_izq)

    agregar_simbolos(tokens)


def revisar_endwhile(tokens):
    if quitar_punto_y_coma(tokens) == ["endwhile"]:
        agregar_simbolos(tokens)


# revision de funciones
def abrir_funcion(nombre, tipo, parametros, renglon):
    locales = {}
    for tipo_parametro, nombre_parametro in parametros:
        if re.fullmatch(REGEX_NOMBRE, nombre_parametro) is None:
            agregar_error(nombre_parametro, renglon, "Variable indefinida")
        elif nombre_parametro in locales:
            agregar_error(nombre_parametro, renglon, "Declaración duplicada")
        else:
            locales[nombre_parametro] = tipo_parametro
    funcion_actual.clear()
    funcion_actual["nombre"] = nombre
    funcion_actual["tipo"] = tipo
    funcion_actual["locales"] = locales
    funcion_actual["renglon"] = renglon
    funcion_actual["retorna"] = False


def cerrar_funcion():
    tipo = funcion_actual["tipo"]
    if tipo in TIPOS and not funcion_actual["retorna"]:
        agregar_error(funcion_actual["nombre"], funcion_actual["renglon"], "Incompatibilidad de tipos, " + tipo)
    funcion_actual.clear()


def revisar_funcion(tokens, renglon):
    cuerpo = quitar_punto_y_coma(tokens)
    if cuerpo[-1] == "{":
        cuerpo = cuerpo[:-1]

    tipo = None
    if cuerpo[0] in TIPOS or cuerpo[0] == "void":
        tipo = cuerpo[0]
        cuerpo = cuerpo[1:]

    if len(cuerpo) < 3 or cuerpo[1] != "(" or cuerpo[-1] != ")":
        return
    nombre = cuerpo[0]
    parametros = leer_parametros(cuerpo[2:-1])
    if parametros is None:
        return

    if funcion_actual:
        cerrar_funcion()

    if tipo is None or re.fullmatch(REGEX_NOMBRE, nombre) is None:
        agregar_error(nombre, renglon, "Función indefinida")
    elif nombre in funciones:
        agregar_error(nombre, renglon, "Declaración duplicada")
    else:
        funciones[nombre] = (tipo, [tipo_parametro for tipo_parametro, _ in parametros])

    abrir_funcion(nombre, tipo, parametros, renglon)
    agregar_simbolos(tokens)


def revisar_retorno(tokens, renglon):
    if not funcion_actual:
        return
    funcion_actual["retorna"] = True
    tipo = funcion_actual["tipo"]
    expresion = quitar_punto_y_coma(tokens)[1:]

    if tipo == "void":
        agregar_error("return", renglon, "Incompatibilidad de tipos, void")
    elif tipo is not None:
        if expresion == []:
            agregar_error("return", renglon, "Incompatibilidad de tipos, " + tipo)
        else:
            if len(expresion) == 1 and expresion[0] in TIPOS:
                elementos = expresion
            else:
                elementos = leer_expresion(expresion)
            if elementos is not None and not revisar_indefinidas(elementos, renglon):
                revisar_tipos(elementos, tipo, renglon)

    agregar_simbolos(tokens)


def revisar_llaves(tokens):
    cuerpo = quitar_punto_y_coma(tokens)
    if cuerpo == ["{"]:
        agregar_simbolos(tokens)
    elif cuerpo == ["}"]:
        if funcion_actual:
            cerrar_funcion()
        agregar_simbolos(tokens)


def revisar_llamada(tokens, renglon):
    elementos = leer_expresion(quitar_punto_y_coma(tokens))
    if elementos is None or len(elementos) != 1 or not isinstance(elementos[0], tuple):
        return
    if not revisar_indefinidas(elementos, renglon):
        revisar_argumentos(elementos[0], renglon)
    agregar_simbolos(tokens)


# analisis del codigo
def analizar_linea(linea, renglon):
    tokens = re.findall(PATRON_TOKENS, linea)

    for i in range(len(tokens)):
        if re.fullmatch(r"-\s+-", tokens[i]):
            tokens[i] = "--"

    for t in tokens:
        if not es_conocido(t):
            return

    primero = tokens[0]
    if primero == "void":
        revisar_funcion(tokens, renglon)
    elif primero in TIPOS:
        if len(tokens) > 2 and es_palabra(tokens[1]) and tokens[2] == "(":
            revisar_funcion(tokens, renglon)
        else:
            revisar_declaracion(tokens, renglon)
    elif primero == "while":
        revisar_while(tokens, renglon)
    elif primero == "endwhile":
        revisar_endwhile(tokens)
    elif primero == "return":
        revisar_retorno(tokens, renglon)
    elif primero == "{" or primero == "}":
        revisar_llaves(tokens)
    elif es_palabra(primero):
        if len(tokens) > 1 and tokens[1] == "(":
            if "{" in tokens or any(t in TIPOS for t in tokens):
                revisar_funcion(tokens, renglon)
            else:
                revisar_llamada(tokens, renglon)
        else:
            revisar_asignacion(tokens, renglon)


def analizar_codigo(codigo):
    tabla_simbolos.clear()
    tabla_errores.clear()
    errores_pendientes.clear()
    variables.clear()
    funciones.clear()
    funcion_actual.clear()

    renglon = 0
    for linea in codigo.split("\n"):
        renglon = renglon + 1
        linea = linea.strip()
        if linea != "":
            analizar_linea(linea, renglon)

    if funcion_actual:
        cerrar_funcion()

    errores_pendientes.sort(key=lambda error: error[0])
    numero = 0
    for renglon, lexema, descripcion in errores_pendientes:
        numero = numero + 1
        tabla_errores.append(("ErrSem" + str(numero), lexema, renglon, descripcion))


# parte de interfaz
def crear_tabla(padre, columnas):
    marco = tk.Frame(padre)
    marco.pack(fill="both", expand=True)
    ids = [c[0] for c in columnas]
    tabla = ttk.Treeview(marco, columns=ids, show="headings", height=12)
    for ident, titulo, ancho in columnas:
        tabla.heading(ident, text=titulo)
        tabla.column(ident, width=ancho)
    barra = ttk.Scrollbar(marco, orient="vertical", command=tabla.yview)
    tabla.configure(yscrollcommand=barra.set)
    tabla.pack(side="left", fill="both", expand=True)
    barra.pack(side="right", fill="y")
    return tabla


def main():
    ventana = tk.Tk()
    ventana.title("Compilador de errores semánticos - Equipo 6")
    ventana.geometry("1050x720")

    tk.Label(ventana, text="Escribe aquí el código:", font=("Arial", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 0))

    letra = ("Courier New", 11)
    marco_codigo = tk.Frame(ventana, relief="solid", borderwidth=1)
    marco_codigo.pack(fill="x", padx=10, pady=5)
    marco_codigo.columnconfigure(1, weight=1)

    numeros = tk.Text(marco_codigo, width=4, height=14, font=letra, bg="#e8e8e8", fg="#666666",
                      state="disabled", cursor="arrow", takefocus=0,
                      borderwidth=0, highlightthickness=0, padx=4, pady=4)
    numeros.tag_configure("derecha", justify="right")
    caja_codigo = tk.Text(marco_codigo, height=14, font=letra, wrap="none", undo=True,
                          borderwidth=0, highlightthickness=0, padx=4, pady=4)
    barra_y = ttk.Scrollbar(marco_codigo, orient="vertical")
    barra_x = ttk.Scrollbar(marco_codigo, orient="horizontal", command=caja_codigo.xview)

    numeros.grid(row=0, column=0, sticky="ns")
    caja_codigo.grid(row=0, column=1, sticky="nsew")
    barra_y.grid(row=0, column=2, sticky="ns")
    barra_x.grid(row=1, column=1, sticky="ew")

    def mover_barra(*args):
        caja_codigo.yview(*args)
        numeros.yview(*args)

    def al_desplazar(inicio, fin):
        barra_y.set(inicio, fin)
        numeros.yview_moveto(inicio)

    def actualizar_numeros(evento=None):
        if not caja_codigo.edit_modified():
            return
        total = int(caja_codigo.index("end-1c").split(".")[0])
        numeros.config(state="normal")
        numeros.delete("1.0", "end")
        numeros.insert("1.0", "\n".join(str(n) for n in range(1, total + 1)), "derecha")
        numeros.config(state="disabled")
        numeros.yview_moveto(caja_codigo.yview()[0])
        caja_codigo.edit_modified(False)

    barra_y.config(command=mover_barra)
    caja_codigo.config(yscrollcommand=al_desplazar, xscrollcommand=barra_x.set)
    caja_codigo.bind("<<Modified>>", actualizar_numeros)
    for evento in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        numeros.bind(evento, lambda e: "break")
    caja_codigo.edit_modified(True)
    actualizar_numeros()
    caja_codigo.focus_set()

    def limpiar_tablas():
        for fila in arbol_simbolos.get_children():
            arbol_simbolos.delete(fila)
        for fila in arbol_errores.get_children():
            arbol_errores.delete(fila)

    def boton_analizar():
        analizar_codigo(caja_codigo.get("1.0", "end"))
        limpiar_tablas()
        for simbolo in tabla_simbolos:
            arbol_simbolos.insert("", "end", values=simbolo)
        for error in tabla_errores:
            arbol_errores.insert("", "end", values=error)

    def boton_limpiar():
        caja_codigo.delete("1.0", "end")
        limpiar_tablas()

    botones = tk.Frame(ventana)
    botones.pack(pady=5)
    tk.Button(botones, text="Analizar", width=14, command=boton_analizar).pack(side="left", padx=5)
    tk.Button(botones, text="Limpiar", width=14, command=boton_limpiar).pack(side="left", padx=5)

    marco_tablas = tk.Frame(ventana)
    marco_tablas.pack(fill="both", expand=True, padx=10, pady=5)
    marco_tablas.columnconfigure(0, weight=1)
    marco_tablas.columnconfigure(1, weight=2)
    marco_tablas.rowconfigure(0, weight=1)

    marco_simbolos = tk.LabelFrame(marco_tablas, text="TABLA DE SÍMBOLOS")
    marco_simbolos.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
    arbol_simbolos = crear_tabla(marco_simbolos, [
        ("lexema", "LEXEMA", 150),
        ("tipo", "TIPO DE DATO", 120),
    ])

    marco_errores = tk.LabelFrame(marco_tablas, text="TABLA DE ERRORES")
    marco_errores.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
    arbol_errores = crear_tabla(marco_errores, [
        ("token", "TOKEN", 80),
        ("lexema", "LEXEMA", 100),
        ("renglon", "RENGLÓN", 70),
        ("descripcion", "DESCRIPCIÓN", 380),
    ])

    ventana.mainloop()


if __name__ == "__main__":
    main()