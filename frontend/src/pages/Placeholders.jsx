import { PageHeader } from "@/components/common";
import { Card } from "@/components/ui/card";
import { Construction } from "lucide-react";

export function Placeholder({ title, subtitle, note }) {
  return (
    <div>
      <PageHeader title={title} subtitle={subtitle} />
      <Card className="border-border bg-card p-12 text-center">
        <Construction className="mx-auto h-10 w-10 text-sky-400/60" />
        <p className="mt-4 text-sm text-muted-foreground max-w-md mx-auto">{note}</p>
      </Card>
    </div>
  );
}

export const Cameras = () => <Placeholder title="Câmeras" subtitle="Vínculo de câmeras aos pontos de acesso" note="Módulo de câmeras (vínculo e visualização) será implementado em iteração futura." />;
export const Reception = () => <Placeholder title="Portaria / Recepção" subtitle="Check-in e check-out de visitantes" note="Fluxo de portaria (check-in com captura de foto, entrega de cartão/QR, check-out e expiração) será implementado na etapa de Visitantes." />;
export const Schedules = () => <Placeholder title="Agendamentos" subtitle="Agendamento de visitas" note="Agendamento de visitas com anfitrião e QR temporário por e-mail será implementado na etapa de Visitantes." />;
export const Integrations = () => <Placeholder title="Integrações" subtitle="API, Webhooks e MQTT" note="Configuração de API/Swagger, webhooks de eventos e publicação MQTT será implementada em iteração futura." />;
export const Shortcuts = () => <Placeholder title="Atalhos" subtitle="Atalhos personalizados" note="Personalização de atalhos do operador será implementada em iteração futura." />;
export const Backup = () => <Placeholder title="Backup" subtitle="Backup do banco de dados" note="Agendamento e download de backup será implementado em iteração futura." />;
