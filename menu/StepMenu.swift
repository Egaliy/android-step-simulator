import AppKit

let root = Bundle.main.object(forInfoDictionaryKey: "StepLabRoot") as! String
let runtime = root + "/work/daily-steps.nosync"
func json(_ path: String) -> [String:Any] {
    guard let data = FileManager.default.contents(atPath:path), let value = try? JSONSerialization.jsonObject(with:data) as? [String:Any] else {return [:]}
    return value
}
let iso = ISO8601DateFormatter()
class App: NSObject, NSApplicationDelegate {
    var item: NSStatusItem!
    let pop = NSPopover()
    let steps = NSTextField(string:"8000")
    let minutes = NSTextField(string:"80")
    let state = NSTextField(wrappingLabelWithString:"Готово к запуску")
    let count = NSTextField(labelWithString:"Записано: —")
    let timeline = NSTextField(labelWithString:"Сессия ещё не началась")
    let progress = NSProgressIndicator()
    let detail = NSTextField(wrappingLabelWithString:"Записи поступают раз в минуту. Синхронизация со спортзалом может задерживаться.")
    var timer: Timer?
    var task: Process?
    var startButton: NSButton!
    var stopButton: NSButton!
    var offButton: NSButton!
    var sessionBase = 0
    func label(_ text:String, _ size:CGFloat = 13) -> NSTextField {
        let v = NSTextField(labelWithString:text);v.font = .systemFont(ofSize:size);return v
    }
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        item = NSStatusBar.system.statusItem(withLength:NSStatusItem.variableLength)
        item.button?.image = NSImage(systemSymbolName:"figure.walk",accessibilityDescription:"Step Simulator")
        item.button?.imagePosition = .imageLeading
        item.button?.target=self;item.button?.action=#selector(toggle)
        let vc=NSViewController();vc.view=NSView(frame:NSRect(x:0,y:0,width:360,height:480))
        let stack=NSStackView();stack.orientation = .vertical;stack.alignment = .leading;stack.spacing=12
        stack.translatesAutoresizingMaskIntoConstraints=false;vc.view.addSubview(stack)
        NSLayoutConstraint.activate([stack.leadingAnchor.constraint(equalTo:vc.view.leadingAnchor,constant:20),stack.trailingAnchor.constraint(equalTo:vc.view.trailingAnchor,constant:-20),stack.topAnchor.constraint(equalTo:vc.view.topAnchor,constant:20)])
        stack.addArrangedSubview(label("Step Simulator",20))
        let sub=label("Тестовая сессия · ручной ввод",11);sub.textColor = .secondaryLabelColor;stack.addArrangedSubview(sub)
        let fields=NSStackView(views:[label("Шагов"),steps,label("Минут"),minutes]);fields.spacing=8
        steps.widthAnchor.constraint(equalToConstant:80).isActive=true;minutes.widthAnchor.constraint(equalToConstant:55).isActive=true
        stack.addArrangedSubview(fields)
        startButton=NSButton(title:"Начать сессию",target:self,action:#selector(start));startButton.bezelStyle = .rounded
        stopButton=NSButton(title:"Остановить",target:self,action:#selector(stop));stopButton.bezelStyle = .rounded
        stack.addArrangedSubview(NSStackView(views:[startButton,stopButton]))
        state.font = .systemFont(ofSize:12);state.widthAnchor.constraint(equalToConstant:320).isActive=true;stack.addArrangedSubview(state)
        count.font = .monospacedDigitSystemFont(ofSize:18,weight:.medium);stack.addArrangedSubview(count)
        progress.isIndeterminate=false;progress.minValue=0;progress.maxValue=1;progress.style = .bar;progress.widthAnchor.constraint(equalToConstant:320).isActive=true;stack.addArrangedSubview(progress)
        timeline.font = .monospacedDigitSystemFont(ofSize:11,weight:.regular);stack.addArrangedSubview(timeline)
        detail.font = .systemFont(ofSize:11);detail.textColor = .secondaryLabelColor;detail.widthAnchor.constraint(equalToConstant:320).isActive=true;stack.addArrangedSubview(detail)
        offButton=NSButton(title:"Выключить Android и освободить память",target:self,action:#selector(shutdown));offButton.bezelStyle = .rounded;stack.addArrangedSubview(offButton)
        let quit=NSButton(title:"Закрыть меню (сессия продолжится)",target:self,action:#selector(quitApp));quit.isBordered=false;quit.font = .systemFont(ofSize:11);stack.addArrangedSubview(quit)
        pop.contentViewController=vc;pop.contentSize=vc.view.frame.size;pop.behavior = .transient
        timer=Timer.scheduledTimer(withTimeInterval:1,repeats:true){[weak self] _ in self?.refresh()};refresh()
        if CommandLine.arguments.contains("--show") {toggle()}
        if let i=CommandLine.arguments.firstIndex(of:"--snapshot"),CommandLine.arguments.count>i+1 {
            DispatchQueue.main.asyncAfter(deadline:.now()+1) {
                vc.view.layoutSubtreeIfNeeded()
                if let rep=vc.view.bitmapImageRepForCachingDisplay(in:vc.view.bounds) {
                    vc.view.cacheDisplay(in:vc.view.bounds,to:rep)
                    if let data=rep.representation(using:.png,properties:[:]) {try? data.write(to:URL(fileURLWithPath:CommandLine.arguments[i+1]))}
                }
            }
        }
    }
    @objc func toggle(){if pop.isShown {pop.performClose(nil)}else if let b=item.button {pop.show(relativeTo:b.bounds,of:b,preferredEdge:.minY);NSApp.activate(ignoringOtherApps:true)}}
    func run(_ action:String) {
        if task?.isRunning == true {return}
        let p=Process();p.executableURL=URL(fileURLWithPath:"/usr/bin/python3")
        p.arguments=[runtime+"/code/menu_control.py",action,"--steps",steps.stringValue,"--minutes",minutes.stringValue]
        var env=ProcessInfo.processInfo.environment;env["STEP_LAB_ROOT"]=root;env["ANDROID_HOME"]=Bundle.main.object(forInfoDictionaryKey:"StepLabSDK") as? String;p.environment=env
        let log=runtime+"/menu-control.log";if !FileManager.default.fileExists(atPath:log){FileManager.default.createFile(atPath:log,contents:nil)}
        if let out=FileHandle(forWritingAtPath:log){out.seekToEndOfFile();p.standardOutput=out;p.standardError=out}
        p.standardInput=FileHandle.nullDevice
        p.terminationHandler={_ in DispatchQueue.main.async {self.refresh()}}
        do {try p.run();task=p;state.stringValue="Подготовка…";refresh()}catch{state.stringValue=error.localizedDescription}
    }
    @objc func start(){
        guard let s=Int(steps.stringValue),let m=Int(minutes.stringValue),s>0,s<=50000,m>0,m<=720,s<=m*180 else {state.stringValue="Проверьте шаги и минуты (не более 180 шагов/мин).";return}
        run("start")
    }
    @objc func stop(){run("stop")}
    @objc func shutdown(){run("shutdown")}
    @objc func quitApp(){NSApp.terminate(nil)}
    func refresh(){
        let status=json(runtime+"/status.json"),control=json(runtime+"/control.json")
        let busy=task?.isRunning == true
        startButton.isEnabled = !busy;stopButton.isEnabled = !busy;offButton.isEnabled = !busy
        let pid=status["pid"] as? Int32 ?? 0
        let alive=pid>0 && kill(pid,0)==0 && status["state"] as? String != "stopped"
        let total=status["confirmed_health_connect"] as? Int ?? 0
        item.button?.title=" \(total)"
        if busy {state.stringValue=control["message"] as? String ?? "Подготовка…"}
        else if control["state"] as? String == "error" {state.stringValue=control["message"] as? String ?? "Ошибка"}
        else if alive {state.stringValue=status["last_error"] as? String ?? "Работает в фоне · Health Connect"}
        else {state.stringValue="Остановлено · можно начать новую сессию"}
        let day=status["date"] as? String ?? ""
        let plan=json(runtime+"/\(day)-plan.json")
        if let session=plan["session"] as? [String:Any],let a=session["start"] as? String,let z=session["end"] as? String,let begin=iso.date(from:a),let end=iso.date(from:z){
            let goal=session["steps"] as? Int ?? 0,base=session["baseline"] as? Int ?? 0
            let done=max(0,total-base);count.stringValue="\(done) / \(goal) шагов записано"
            progress.doubleValue=goal>0 ? min(1,Double(done)/Double(goal)):0
            let f=DateFormatter();f.timeZone=TimeZone(identifier:"Europe/Belgrade");f.dateFormat="HH:mm"
            let elapsed=max(0,min(Int(end.timeIntervalSince(begin)/60),Int(Date().timeIntervalSince(begin)/60)))
            timeline.stringValue="\(f.string(from:begin)) → \(f.string(from:end)) · прошло \(elapsed) мин"
            if alive && Date()>end && status["pending"] is NSNull {state.stringValue=done>=goal ? "Сессия завершена" : "Сессия завершена с пропусками"}
        }else{count.stringValue="Всего записано: \(total)";progress.doubleValue=0;timeline.stringValue="Сессия ещё не началась"}
    }
}
let app=NSApplication.shared
let delegate=App();app.delegate=delegate
app.run()
