import re
import os
import tkinter as tk
from tkinter import ttk

# datos del lenguaje
TIPOS = ["ENTER", "REALER", "CADER"]
PALABRAS_RESERVADAS = TIPOS + ["void", "while", "endwhile", "return"]

REGEX_NOMBRE = r"re[A-Z][a-z]+"

OPERADORES = ["+", "-", "*", "/"]
RELACIONALES = [">", "<", ">=", "<=", "==", "!="]
SIMBOLOS = ["(", ")", ",", ";", ":", "=", "--", "++", "{", "}", "&&", "||"] + OPERADORES + RELACIONALES

OPERADORES_PERMITIDOS = {
    "ENTER": ["+", "-", "*"],
    "REALER": ["+", "-", "*", "/"],
    "CADER": ["+", "-"],
}

PATRON_TOKENS = r'[“"][^”"]*[”"]|\d+\.\d+|\d+|[^\W\d]\w*|-\s*-|\+\+|&&|\|\||[<>=!]=|[+\-*/(),;:<>={}]|\S'

# tablas
tabla_simbolos = []
tabla_errores = []
errores_pendientes = []
variables = {}
funciones = {}
funcion_actual = {}
tabla_triplo = []
temporales = []
funciones_triplo = {}
ciclos_triplo = []
expandiendo = []


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
    abiertos = 0
    while i < len(partes):
        t = partes[i]
        if espero_operando:
            if t == "(":
                abiertos = abiertos + 1
                elementos.append(t)
                i = i + 1
                continue
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
            if t == ")" and abiertos > 0:
                abiertos = abiertos - 1
            elif t in OPERADORES:
                espero_operando = True
            elif not (t in ["--", "++"] and i == len(partes) - 1):
                return None
            elementos.append(t)
            i = i + 1
    if espero_operando or abiertos != 0:
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
        elif e in ["(", ")"]:
            continue
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
    triplo_asignacion(destino, elementos)


def separar_condiciones(partes):
    condiciones = [[]]
    conectores = []
    for t in partes:
        if t in ["&&", "||"]:
            conectores.append(t)
            condiciones.append([])
        else:
            condiciones[-1].append(t)
    return condiciones, conectores


def condicion_bien_escrita(condicion):
    # while ( TIPO variable relacional operando )  o  while ( variable relacional operando )
    if len(condicion) == 4 and condicion[0] in TIPOS:
        return (es_palabra(condicion[1]) and
                (condicion[2] in RELACIONALES or condicion[2] == "=") and
                es_operando(condicion[3]))
    return (len(condicion) == 3 and es_operando(condicion[0]) and
            (condicion[1] in RELACIONALES or condicion[1] == "=") and
            es_operando(condicion[2]))


def revisar_condicion(condicion, renglon, ya_reportadas):
    if condicion[0] in TIPOS:
        izquierda = condicion[1]
        derecha = condicion[3]
        ambito = ambito_actual()
        if re.fullmatch(REGEX_NOMBRE, izquierda) is None:
            agregar_error(izquierda, renglon, "Variable indefinida")
        elif izquierda in ambito:
            agregar_error(izquierda, renglon, "Declaración duplicada")
        else:
            ambito[izquierda] = condicion[0]
        elementos_a_revisar = [derecha]
    else:
        izquierda = condicion[0]
        derecha = condicion[2]
        elementos_a_revisar = [izquierda, derecha]

    nuevos = [e for e in elementos_a_revisar if e not in ya_reportadas]
    ya_reportadas.extend(nuevos)
    if not revisar_indefinidas(nuevos, renglon):
        tipo_izq = tipo_de(izquierda)
        tipo_der = tipo_de(derecha)
        if tipo_izq != "" and tipo_der != "" and not es_compatible(tipo_izq, tipo_der):
            agregar_error(derecha, renglon, "Incompatibilidad de tipos, " + tipo_izq)


def revisar_while(tokens, renglon):
    cuerpo = quitar_punto_y_coma(tokens)
    if len(cuerpo) < 3 or cuerpo[1] != "(" or cuerpo[-1] != ")":
        return

    condiciones, conectores = separar_condiciones(cuerpo[2:-1])
    for condicion in condiciones:
        if not condicion_bien_escrita(condicion):
            return

    ya_reportadas = []
    for condicion in condiciones:
        revisar_condicion(condicion, renglon, ya_reportadas)

    agregar_simbolos(tokens)
    triplo_while(condiciones, conectores)


def revisar_endwhile(tokens):
    if quitar_punto_y_coma(tokens) == ["endwhile"]:
        agregar_simbolos(tokens)
        triplo_endwhile()


def revisar_incremento(tokens, renglon):
    cuerpo = quitar_punto_y_coma(tokens)
    revisar_indefinidas([cuerpo[0]], renglon)
    agregar_simbolos(tokens)
    triplo_asignacion(cuerpo[0], [cuerpo[0], cuerpo[1][0], "1"])


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
    triplo_cerrar_funcion(funcion_actual["triplo"])
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
    funcion_actual["triplo"] = triplo_abrir_funcion(nombre, parametros)
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
    triplo_retorno(funcion_actual["triplo"], expresion)


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
    temporales.clear()
    triplo_llamada(elementos[0], False)


# generacion del triplo (posfijo)
PRECEDENCIA = {"+": 1, "-": 1, "*": 2, "/": 2}


def siguiente_fila():
    return len(tabla_triplo) + 1


def agregar_triplo(objeto, fuente, operador):
    tabla_triplo.append([siguiente_fila(), objeto, fuente, operador])
    return len(tabla_triplo)


def nuevo_temporal():
    numero = 1
    while "T" + str(numero) in temporales:
        numero = numero + 1
    temporales.append("T" + str(numero))
    return "T" + str(numero)


def liberar_temporal(dato):
    if dato in temporales:
        temporales.remove(dato)


def a_posfijo(elementos):
    salida = []
    pila = []
    for e in elementos:
        if e == "(":
            pila.append(e)
        elif e == ")":
            while pila[-1] != "(":
                salida.append(pila.pop())
            pila.pop()
        elif isinstance(e, str) and e in OPERADORES:
            while pila and pila[-1] != "(" and PRECEDENCIA[pila[-1]] >= PRECEDENCIA[e]:
                salida.append(pila.pop())
            pila.append(e)
        else:
            salida.append(e)
    while pila:
        salida.append(pila.pop())
    return salida


def triplo_expresion(elementos):
    if len(elementos) > 1 and elementos[-1] in ["--", "++"]:
        elementos = elementos[:-1] + [elementos[-1][0], "1"]

    pila = []
    for e in a_posfijo(elementos):
        if isinstance(e, tuple):
            pila.append(triplo_llamada(e, True))
        elif e in OPERADORES:
            derecha = pila.pop()
            izquierda = pila.pop()
            if izquierda not in temporales:
                temporal = nuevo_temporal()
                agregar_triplo(temporal, izquierda, "=")
                izquierda = temporal
            agregar_triplo(izquierda, derecha, e)
            liberar_temporal(derecha)
            pila.append(izquierda)
        else:
            pila.append(e)

    resultado = pila.pop()
    if resultado not in temporales:
        temporal = nuevo_temporal()
        agregar_triplo(temporal, resultado, "=")
        resultado = temporal
    return resultado


def triplo_asignacion(destino, elementos):
    temporales.clear()
    resultado = triplo_expresion(elementos)
    agregar_triplo(destino, resultado, "=")
    temporales.clear()


def triplo_llamada(llamada, con_valor):
    nombre = llamada[1]
    argumentos = llamada[2]
    if nombre not in funciones_triplo:
        return nombre
    datos = funciones_triplo[nombre]

    for i in range(min(len(argumentos), len(datos["parametros"]))):
        temporal = nuevo_temporal()
        agregar_triplo(temporal, argumentos[i], "=")
        agregar_triplo(datos["parametros"][i], temporal, "=")
        liberar_temporal(temporal)
    agregar_triplo("", datos["inicio"], "JMP")

    if datos["regreso"] is None:
        datos["regreso"] = siguiente_fila()
        for fila in datos["saltos_return"]:
            tabla_triplo[fila - 1][2] = datos["regreso"]

    if not con_valor:
        return None
    if datos["valor"] is None or nombre in expandiendo:
        return nombre
    expandiendo.append(nombre)
    resultado = triplo_expresion(datos["valor"])
    expandiendo.remove(nombre)
    return resultado


def triplo_abrir_funcion(nombre, parametros):
    salto = agregar_triplo("", "", "JMP")
    datos = {
        "salto": salto,
        "inicio": siguiente_fila(),
        "parametros": [nombre_parametro for _, nombre_parametro in parametros],
        "saltos_return": [],
        "regreso": None,
        "valor": None,
        "tiene_return": False,
    }
    if nombre not in funciones_triplo:
        funciones_triplo[nombre] = datos
    return datos


def triplo_cerrar_funcion(datos):
    if not datos["tiene_return"]:
        datos["saltos_return"].append(agregar_triplo("", datos["regreso"] or "", "JMP"))
    fin = siguiente_fila()
    tabla_triplo[datos["salto"] - 1][2] = fin
    if datos["regreso"] is None:
        for fila in datos["saltos_return"]:
            tabla_triplo[fila - 1][2] = fin


def triplo_retorno(datos, expresion):
    datos["tiene_return"] = True
    if len(expresion) == 1 and expresion[0] in TIPOS:
        datos["valor"] = expresion
    elif expresion != []:
        elementos = leer_expresion(expresion)
        if elementos is not None:
            datos["valor"] = elementos
    datos["saltos_return"].append(agregar_triplo("", datos["regreso"] or "", "JMP"))


def triplo_while(condiciones, conectores):
    ciclo = {"inicio": siguiente_fila(), "salidas": []}
    inicios = []
    filas_true = []
    filas_false = []
    for condicion in condiciones:
        if condicion[0] in TIPOS:
            condicion = condicion[1:]
        temporales.clear()
        inicios.append(siguiente_fila())
        temporal = nuevo_temporal()
        agregar_triplo(temporal, condicion[0], "=")
        agregar_triplo(temporal, condicion[2], condicion[1])
        filas_true.append(agregar_triplo("", "TRUE", ""))
        filas_false.append(agregar_triplo("", "FALSE", ""))
    temporales.clear()

    for i in range(len(condiciones)):
        if i < len(conectores) and conectores[i] == "&&":
            tabla_triplo[filas_true[i] - 1][3] = inicios[i + 1]
        else:
            tabla_triplo[filas_true[i] - 1][3] = siguiente_fila()

        destino = None
        for j in range(i, len(conectores)):
            if conectores[j] == "||":
                destino = inicios[j + 1]
                break
        if destino is None:
            ciclo["salidas"].append(filas_false[i])
        else:
            tabla_triplo[filas_false[i] - 1][3] = destino

    ciclos_triplo.append(ciclo)


def triplo_endwhile():
    if not ciclos_triplo:
        return
    ciclo = ciclos_triplo.pop()
    agregar_triplo("", ciclo["inicio"], "JMP")
    for fila in ciclo["salidas"]:
        tabla_triplo[fila - 1][3] = siguiente_fila()


def terminar_triplo():
    for ciclo in ciclos_triplo:
        for fila in ciclo["salidas"]:
            tabla_triplo[fila - 1][3] = siguiente_fila()
    if tabla_triplo:
        agregar_triplo("", "", "")


# archivo del triplo
def guardar_triplo():
    carpeta = os.path.dirname(os.path.abspath(__file__))
    encabezados = ["N. de fila", "Dato Objeto", "Dato Fuente", "Operador"]
    filas = [encabezados] + [[str(dato) for dato in fila] for fila in tabla_triplo]
    anchos = [max(len(fila[i]) for fila in filas) + 2 for i in range(4)]
    separador = "+" + "+".join("-" * ancho for ancho in anchos) + "+"

    with open(os.path.join(carpeta, "triplo.txt"), "w", encoding="utf-8") as archivo:
        archivo.write(separador + "\n")
        for numero, fila in enumerate(filas):
            archivo.write("|" + "|".join(fila[i].center(anchos[i]) for i in range(4)) + "|\n")
            if numero == 0:
                archivo.write(separador + "\n")
        archivo.write(separador + "\n")


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
        elif quitar_punto_y_coma(tokens)[1:] in [["--"], ["++"]]:
            revisar_incremento(tokens, renglon)
        else:
            revisar_asignacion(tokens, renglon)


def analizar_codigo(codigo):
    tabla_simbolos.clear()
    tabla_errores.clear()
    errores_pendientes.clear()
    variables.clear()
    funciones.clear()
    funcion_actual.clear()
    tabla_triplo.clear()
    temporales.clear()
    funciones_triplo.clear()
    ciclos_triplo.clear()
    expandiendo.clear()

    renglon = 0
    for linea in codigo.split("\n"):
        renglon = renglon + 1
        linea = linea.strip()
        if linea != "":
            analizar_linea(linea, renglon)

    if funcion_actual:
        cerrar_funcion()
    terminar_triplo()

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
        guardar_triplo()

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
