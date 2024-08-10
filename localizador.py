from pynput import mouse

def on_click(x, y, button, pressed):
    if pressed:
        print(f'Posição do mouse: x={x}, y={y}')

# Configura o listener para capturar os cliques do mouse
with mouse.Listener(on_click=on_click) as listener:
    listener.join()
