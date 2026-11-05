import SwiftUI

@MainActor final class LightCalibrationModel:ObservableObject {
    @Published var draft=HueCalibration.load()
    @Published var referenceID="navy"
    @Published var error:String?
    private let api:WatchAPI
    private var heartbeat:Task<Void,Never>?
    private var previewTask:Task<Void,Never>?
    private var closed=false
    var reference:HueReference {HueReference.colours.first {$0.id==referenceID} ?? HueReference.colours[5]}
    var outputHue:Double {draft.corrected(reference.hue)}
    init(api:WatchAPI) {self.api=api}
    func start() {
        closed=false;heartbeat?.cancel()
        heartbeat=Task { [weak self] in
            while !Task.isCancelled {
                guard let self,!self.closed else {return}
                await self.preview()
                do {try await Task.sleep(for:.seconds(2))} catch {return}
            }
        }
    }
    private func preview()async {
        do {try await api.previewSceneCalibration(hue:outputHue);if !closed {error=nil}}
        catch is CancellationError {}
        catch {if !closed,!Task.isCancelled {self.error=error.localizedDescription}}
    }
    func changed() {
        previewTask?.cancel()
        previewTask=Task { [weak self] in
            do {try await Task.sleep(for:.milliseconds(300))} catch {return}
            guard let self,!self.closed else {return};await self.preview()
        }
    }
    func adjust(_ amount:Double) {draft.adjust(reference,by:amount);changed()}
    func resetColour() {draft.offsets.removeValue(forKey:referenceID);changed()}
    func resetAll() {draft=HueCalibration();changed()}
    func save()->Bool {
        do {try draft.save();return true} catch {self.error="Could not save calibration. Please try again.";return false}
    }
    func stop() {
        guard !closed else {return};closed=true;heartbeat?.cancel();previewTask?.cancel();heartbeat=nil;previewTask=nil
        let api=api;Task {await api.endSceneCalibration()}
    }
}

struct SceneLightingCalibration:View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var model:LightCalibrationModel
    @State private var resetConfirmation=false
    init(api:WatchAPI) {_model=StateObject(wrappedValue:LightCalibrationModel(api:api))}
    var body:some View {
        ZStack(alignment:.bottom) {
            Color(hue:model.reference.hue/360,saturation:model.reference.saturation,brightness:model.reference.value).ignoresSafeArea()
            VStack(alignment:.leading,spacing:20) {
                HStack(alignment:.firstTextBaseline) {
                    Text("Match Behind TV to this colour").font(.system(size:32,weight:.semibold))
                    Spacer()
                    Text(model.reference.title).font(.system(size:27,weight:.medium))
                }
                Text("Match the hue, rather than how dark the swatch is. Lamp brightness stays unchanged; saturation stays at 100%.")
                    .font(.system(size:22)).foregroundStyle(.white.opacity(0.7))
                HStack(spacing:20) {
                    Menu {
                        Picker("Reference colour",selection:$model.referenceID) {
                            ForEach(HueReference.colours) {reference in Text(reference.title).tag(reference.id)}
                        }
                    } label: {Label("Colour",systemImage:"paintpalette")}
                    Button("−5°") {model.adjust(-5)}
                    Button("−1°") {model.adjust(-1)}
                    Text("Lamp hue \(Int(model.outputHue.rounded()))°").monospacedDigit().frame(width:205)
                    Button("+1°") {model.adjust(1)}
                    Button("+5°") {model.adjust(5)}
                    Spacer(minLength:0)
                    Button("Reset colour") {model.resetColour()}
                }.font(.system(size:23,weight:.medium)).focusSection()
                HStack(spacing:24) {
                    Button("Save calibration") {if model.save() {model.stop();dismiss()}}
                    Button("Cancel") {model.stop();dismiss()}
                    Spacer()
                    Button("Reset all colours") {resetConfirmation=true}
                }.font(.system(size:23,weight:.medium)).focusSection()
                if let error=model.error {Text(error).font(.system(size:20)).foregroundStyle(.orange)}
            }.padding(.horizontal,64).padding(.vertical,32)
                .foregroundStyle(.white).background(.black.opacity(0.82))
                .buttonStyle(WatchActionButtonStyle()).focusEffectDisabled()
        }.task {model.start()}
            .onChange(of:model.referenceID) {_,_ in model.changed()}
            .onDisappear {model.stop()}
            .onExitCommand {model.stop();dismiss()}
            .confirmationDialog("Reset every reference colour?",isPresented:$resetConfirmation) {
                Button("Reset all",role:.destructive) {model.resetAll()}
                Button("Cancel",role:.cancel) {}
            }
    }
}
