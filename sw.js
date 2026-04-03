self.addEventListener('message', event => {

  if (event.data.tipo === "alerta") {

    self.registration.showNotification("🚨 Alerta de Saúde", {
      body: event.data.msg,
      icon: '/icon.png'
    });

  }

});