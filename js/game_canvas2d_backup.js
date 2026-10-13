(() => {
  'use strict';
  const W=1920,H=1080,LEFT=740,G=1000,AX=860,AY=40,GS=168,S=G/GS;
  const PX=12,PW=716,BAND=420,ITEMY=918,ITEMH=140;
  const MULT=[8,4,2,2,4,8],NAMES=['风暴','机枪','护盾','大球','狙击'];
  const TEAMS=[
    {name:'红队',c:[255,20,70],hi:[255,90,130],glow:[255,40,90],edge:[255,180,200]},
    {name:'绿队',c:[0,230,140],hi:[80,255,200],glow:[0,255,170],edge:[160,255,220]},
    {name:'蓝队',c:[0,140,255],hi:[70,210,255],glow:[40,170,255],edge:[160,220,255]},
    {name:'橙队',c:[255,165,20],hi:[255,220,80],glow:[255,185,40],edge:[255,240,180]}
  ];
  const NEUTRAL=4,BASES=[[120,120],[880,120],[120,880],[880,880]],MAX_SHOTS=5000,MATCH=960;
  const canvas=document.getElementById('game'),ctx=canvas.getContext('2d',{alpha:false});
  const overlay=document.getElementById('overlay'),startpanel=document.getElementById('startpanel'),endpanel=document.getElementById('endpanel');
  const rgb=(a,al)=>al==null?`rgb(${a[0]|0},${a[1]|0},${a[2]|0})`:`rgba(${a[0]|0},${a[1]|0},${a[2]|0},${al})`;
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v)),rand=(a,b)=>a+Math.random()*(b-a),pick=a=>a[(Math.random()*a.length)|0];
  function fmt(v){
    v=Math.max(0,+v||0);
    if(v>=1e6){const n=v/1e6;return (n>=100?n.toFixed(0):n>=10?n.toFixed(2):n.toFixed(2)).replace(/\.?0+$/,'')+'M'}
    if(v>=1e3){const n=v/1e3;return (n>=100?n.toFixed(0):n.toFixed(1)).replace(/\.0$/,'')+'K'}
    return Math.round(v).toLocaleString('en-US');
  }
  function fmtScore(v){v=Math.max(0,Math.round(+v||0));return v.toLocaleString('en-US')}
  function rr(c,x,y,w,h,r,fill,stroke,lw=1){
    c.beginPath();c.moveTo(x+r,y);c.arcTo(x+w,y,x+w,y+h,r);c.arcTo(x+w,y+h,x,y+h,r);c.arcTo(x,y+h,x,y,r);c.arcTo(x,y,x+w,y,r);c.closePath();
    if(fill){c.fillStyle=fill;c.fill()}if(stroke){c.strokeStyle=stroke;c.lineWidth=lw;c.stroke()}
  }
  function nnoise(x,y){return (Math.sin(x*1.73+y*.41)+Math.sin(y*1.31-x*.63)+Math.sin((x+y)*.91)*.55)/2.55}

  /* ---- prebaked glow sprites (avoid per-particle shadowBlur) ---- */
  function bakeGlow(size,stops){
    const cv=document.createElement('canvas');cv.width=cv.height=size;
    const g=cv.getContext('2d'),R=size/2,grd=g.createRadialGradient(R,R,0,R,R,R);
    for(const [t,col] of stops)grd.addColorStop(t,col);
    g.fillStyle=grd;g.fillRect(0,0,size,size);return cv;
  }
  const SPR={
    whiteSoft:bakeGlow(64,[[0,'rgba(255,255,255,1)'],[.25,'rgba(255,255,255,.55)'],[.55,'rgba(200,230,255,.18)'],[1,'rgba(0,0,0,0)']]),
    whiteCore:bakeGlow(24,[[0,'#fff'],[.35,'rgba(255,255,255,.85)'],[1,'rgba(255,255,255,0)']]),
    spark:bakeGlow(20,[[0,'#fff'],[.4,'rgba(255,255,220,.7)'],[1,'rgba(255,200,100,0)']]),
    team:TEAMS.map(t=>bakeGlow(96,[
      [0,rgb(t.hi,1)],[.2,rgb(t.c,.85)],[.5,rgb(t.glow,.35)],[1,rgb(t.glow,0)]
    ]))
  };

  class Game{
    constructor(player){
      this.player=player;this.t=0;this.paused=false;this.over=false;this.winner=-1;this.autoAim=true;this.firing=false;
      this.grid=new Uint8Array(GS*GS).fill(NEUTRAL);this.claimRadius=14;this.expandClock=0;
      this.share=[0,0,0,0];this.level=[0,0,0,0];this.ammo=[25.06e6,25.02e6,24.84e6,25.12e6];
      this.score=[198000,296000,220000,299000];this.shield=[1,1,1,1];
      this.items=[0,0,0,0,0];this.aiItems=Array.from({length:4},()=>[0,0,0,0,0]);this.hit=[0,0,0,0,0,0];
      this.marbles=[];this.nextMarble=[.15,.35,.55,.8];this.cool=[0,0,0,0];
      this.aim=BASES.map(([x,y])=>Math.atan2(G/2-y,G/2-x));this.playerAim=this.aim[player];this.autoFire=true;
      this.shots=[];this.sparks=[];this.frontierSparks=[];this.ribbons=[];this.points=[];
      this.stars=Array.from({length:220},()=>[rand(0,G),rand(0,G),rand(.2,1),rand(.5,2.2)]);
      this.frame=0;this.terrainAge=0;
      this.pegs=this.makePegs();this.lowerPegs=this.makeLowerPegs();
      // terrain buffers
      this.image=document.createElement('canvas');this.image.width=this.image.height=GS;this.ictx=this.image.getContext('2d',{willReadFrequently:true});
      this.img=this.ictx.createImageData(GS,GS);
      this.edge=document.createElement('canvas');this.edge.width=this.edge.height=GS;this.ectx=this.edge.getContext('2d');
      this.edgeImg=this.ectx.createImageData(GS,GS);
      // bloom offscreen (scaled up for soft neon)
      this.bloom=document.createElement('canvas');this.bloom.width=this.bloom.height=GS;this.bctx=this.bloom.getContext('2d');
      this.bloomBig=document.createElement('canvas');this.bloomBig.width=this.bloomBig.height=512;this.bbctx=this.bloomBig.getContext('2d');
      this.dirty=true;this.expandTo(28);
      // seed early marbles + bullets so match feels alive instantly
      for(let t=0;t<4;t++){this.marble(t);this.marble(t);this.marble(t);for(let k=0;k<18;k++)this.spawn(t,0,2)}
    }
    id(x,y){return y*GS+x}
    makePegs(){
      const a=[];const cols=9,rows=7,ox=38,oy=72,dx=78,dy=46;
      for(let row=0;row<rows;row++){
        const n=cols-(row%2?0:0);const x0=ox+(row%2?dx*.5:0);
        for(let col=0;col<n;col++){const x=x0+col*dx;if(x>LEFT-24)continue;a.push([x,oy+row*dy])}
      }
      return a;
    }
    makeLowerPegs(){
      const a=[];const dx=80,dy=52,ox=42,oy=560;
      for(let row=0;row<6;row++){const x0=ox+(row%2?dx*.5:0);for(let col=0;col<9;col++){const x=x0+col*dx;if(x>LEFT-24)continue;a.push([x,oy+row*dy])}}
      return a;
    }
    expandTo(radius){
      this.claimRadius=radius;const r2=radius*radius;
      for(let y=0;y<GS;y++)for(let x=0;x<GS;x++){
        let i=this.id(x,y);if(this.grid[i]!==NEUTRAL)continue;
        let best=1e9,bt=-1;
        for(let t=0;t<4;t++){const [bx,by]=BASES[t],dx=x-bx/S,dy=y-by/S,d=dx*dx+dy*dy;if(d<best){best=d;bt=t}}
        const jitter=nnoise(x*1.1,y*1.1)*14+nnoise(x*.37,y*.51)*9;
        if(best<r2+jitter*radius*.7)this.grid[i]=bt;
      }
      this.dirty=true;
    }
    marble(team){
      const base=1800+this.t*720;
      const mul=pick([1,1,2,2,4,8,16,32,64,128,256]);
      const v=base*mul;
      this.marbles.push({team,x:rand(40,LEFT-40),y:18,vx:rand(-.7,.7),vy:rand(.55,1.5),v,r:v>1e6?18:v>1e5?14:v>2e4?11:7,hit:-1,trail:[]});
    }
    award(team,slot,value){
      const v=value*MULT[slot];
      this.score[team]+=v;this.ammo[team]=Math.min(999e6,this.ammo[team]+v*.6);
      const type=slot%5;
      if(team===this.player)this.items[type]=Math.min(99,this.items[type]+1);
      else this.aiItems[team][type]=Math.min(99,this.aiItems[team][type]+1);
      if(type===2)this.shield[team]=Math.min(1,this.shield[team]+.08);
    }
    spawn(team,kind=0,count=null,angle=null){
      if(this.ammo[team]<800||this.shots.length>=MAX_SHOTS)return;
      const [bx,by]=BASES[team],baseAng=angle??this.aim[team];
      const age=this.t/MATCH;
      // auto evolve kind: early dots → mid beams → late silk
      if(kind===0)kind=age<.12?0:age<.45?1:age<.75?1:4;
      let n=count??(kind===0?6:kind===1?8:kind===4?10:1);
      if(kind===2)n=1;if(kind===3)n=count??7;
      const speed=kind===2?2.2:kind===3?15:kind===4?8.2:kind===1?9.5:7.4;
      const spread=kind===2?0:kind===3?.045:kind===4?.38:kind===1?.34:.2;
      const cost=kind===2?220e3:kind===3?28e3:Math.max(400,n*550);
      this.ammo[team]=Math.max(0,this.ammo[team]-cost);
      for(let k=0;k<n&&this.shots.length<MAX_SHOTS;k++){
        const a=baseAng+(k-(n-1)/2)*spread+rand(-.02,.02);
        const v=rand(speed*.9,speed*1.12);
        this.shots.push({
          team,x:bx+Math.cos(a)*10,y:by+Math.sin(a)*10,
          vx:Math.cos(a)*v,vy:Math.sin(a)*v,kind,life:0,
          value:kind===2?14e6*(1+age*10):kind===3?220e3:14e3,
          trail:[]
        });
      }
    }
    use(team,i){
      const bag=team===this.player?this.items:this.aiItems[team];
      if(bag[i]<=0)return false;bag[i]--;
      const a=this.aim[team];
      if(i===0){for(let k=0;k<42;k++)this.spawn(team,1,1,a+(k-20.5)*.07)}
      if(i===1){for(let k=0;k<14;k++)this.spawn(team,0,3,a+rand(-.28,.28))}
      if(i===2){this.shield[team]=1;this.sparks.push({x:BASES[team][0],y:BASES[team][1],team,life:1,burst:true})}
      if(i===3)this.spawn(team,2,1,a);
      if(i===4)this.spawn(team,3,6,a);
      return true;
    }
    paint(x,y,team,r){
      const gx=Math.round(x/S),gy=Math.round(y/S),gr=Math.max(1,Math.ceil(r/S));
      for(let dy=-gr;dy<=gr;dy++)for(let dx=-gr;dx<=gr;dx++){
        if(dx*dx+dy*dy>gr*gr)continue;
        const xx=gx+dx,yy=gy+dy;if(xx<0||yy<0||xx>=GS||yy>=GS)continue;
        const i=this.id(xx,yy);
        if(this.grid[i]!==team){this.grid[i]=team;this.score[team]=Math.max(0,this.score[team]+35);this.dirty=true}
      }
    }
    hitShot(p){
      const gx=Math.floor(p.x/S),gy=Math.floor(p.y/S);
      if(gx<0||gy<0||gx>=GS||gy>=GS)return true;
      const owner=this.grid[this.id(gx,gy)];
      if(owner===p.team)return false;
      if(owner<4&&this.shield[owner]>.02){
        const [bx,by]=BASES[owner];
        if(Math.hypot(p.x-bx,p.y-by)<100){
          this.shield[owner]=Math.max(0,this.shield[owner]-(p.kind===2?.07:.0025));
          this.sparks.push({x:p.x,y:p.y,team:owner,life:.7});
          return true;
        }
      }
      const radius=p.kind===2?38:p.kind===3?12:p.kind===1?6:p.kind===4?4:3.5;
      this.paint(p.x,p.y,p.team,radius);
      if(Math.random()<.35)this.sparks.push({x:p.x,y:p.y,team:p.team,life:.55+Math.random()*.3});
      if(p.kind===2){p.value*=.995;p.life++;return p.life>240||p.value<700e3}
      return true;
    }
    tickMarbles(dt){
      for(let t=0;t<4;t++){
        this.nextMarble[t]-=dt;
        if(this.nextMarble[t]<=0){
          this.marble(t);
          const pace=clamp(2.1-this.t/420,.42,2.1);
          this.nextMarble[t]=pace*rand(.55,1.15);
          if(this.t>40&&Math.random()<.3)this.marble(t);
        }
      }
      const live=[];
      for(const m of this.marbles){
        m.trail.push([m.x,m.y]);if(m.trail.length>10)m.trail.shift();
        m.vy+=17*dt;m.x+=m.vx*60*dt;m.y+=m.vy*60*dt;
        for(const [x,y] of this.pegs){
          const dx=m.x-x,dy=m.y-y,d=dx*dx+dy*dy;
          if(d<100){const q=Math.sqrt(d)||1;m.vx=(dx/q)*3;m.vy=Math.abs(dy/q)*2.8+1.4;m.x+=dx/q*5;m.y+=dy/q*5}
        }
        if(m.x<8){m.x=8;m.vx=Math.abs(m.vx)}if(m.x>LEFT-8){m.x=LEFT-8;m.vx=-Math.abs(m.vx)}
        if(m.hit<0&&m.y>BAND-4){
          const slot=clamp(Math.floor((m.x-PX)/PW*6),0,5);
          m.hit=slot;this.hit[slot]++;this.award(m.team,slot,m.v);
        }
        if(m.y>ITEMY+20)continue;
        live.push(m);
      }
      this.marbles=live.slice(-130);
    }
    sampleFrontierSparks(){
      // emit ambient sparks along neon frontiers (sampled from edge buffer)
      if(this.frame%4!==0)return;
      const d=this.edgeImg.data;const n=GS*GS;
      let tries=0,added=0;
      while(added<28&&tries<400){
        tries++;
        const i=(Math.random()*n)|0;
        if(d[i*4+3]<200)continue;
        const x=(i%GS)*S+rand(0,S),y=((i/GS)|0)*S+rand(0,S);
        const team=this.grid[i]<4?this.grid[i]:0;
        this.frontierSparks.push({x,y,team,life:.4+Math.random()*.5,vx:rand(-18,18),vy:rand(-18,18)});
        added++;
      }
      if(this.frontierSparks.length>500)this.frontierSparks=this.frontierSparks.slice(-400);
    }
    tick(dt){
      if(this.paused||this.over)return;
      this.t=Math.max(0,this.t+dt);this.frame++;this.expandClock+=dt;
      if(this.expandClock>.35){this.expandClock=0;this.expandTo(Math.min(270,20+this.t*8.2+Math.min(35,this.t*this.t*.05)))}
      for(let t=0;t<4;t++){
        if(this.t<6){const [bx,by]=BASES[t];this.aim[t]=Math.atan2(G/2-by,G/2-bx)}
        else if(t!==this.player||this.autoAim)this.aim[t]+=.26*dt*(1+Math.sin(this.t*.15+t)*.2);
        if(t===this.player&&this.autoAim)this.playerAim=this.aim[t];
        this.cool[t]-=dt;
        const rate=clamp(.14-this.t*.00018,.035,.14);
        if(t===this.player){
          if(!this.autoAim)this.aim[t]=this.playerAim;
          if(this.firing&&this.cool[t]<=0){this.spawn(t,0,this.t<20?8:12);this.cool[t]=.045}
          else if(this.autoFire&&this.cool[t]<=0){this.spawn(t,0,this.t<12?7:this.t<50?10:14);this.cool[t]=rate}
        }else if(this.cool[t]<=0){
          this.spawn(t,0,this.t<12?7:this.t<50?10:14);
          this.cool[t]=rate*(.7+Math.random()*.35);
          if(Math.random()<.0012&&this.aiItems[t].some(v=>v>0)){
            const i=this.aiItems[t].findIndex(v=>v>0);this.use(t,i);
          }
        }
      }
      this.tickMarbles(dt);
      const active=[],trailMax=this.t>80?22:this.t>25?16:12;
      for(const p of this.shots){
        p.trail.push([p.x,p.y]);if(p.trail.length>trailMax)p.trail.shift();
        p.x+=p.vx*60*dt;p.y+=p.vy*60*dt;
        if(p.x<-20||p.y<-20||p.x>G+20||p.y>G+20)continue;
        if(!this.hitShot(p))active.push(p);
      }
      this.shots=active;
      this.sparks=this.sparks.filter(s=>{s.life-=dt*(s.burst?.7:1.8);return s.life>0}).slice(-900);
      for(const s of this.frontierSparks){s.life-=dt*1.4;s.x+=s.vx*dt;s.y+=s.vy*dt}
      this.frontierSparks=this.frontierSparks.filter(s=>s.life>0);
      this.sampleFrontierSparks();
      // cosmetic silk ribbons (visual density without collision cost)
      if(this.frame%2===0){
        for(let t=0;t<4;t++){
          const [bx,by]=BASES[t],a=this.aim[t],n=this.t<15?5:this.t<50?8:10;
          for(let k=0;k<n;k++){
            const ang=a+rand(-.28,.28),sp=rand(8,17);
            this.ribbons.push({team:t,x:bx+rand(-5,5),y:by+rand(-5,5),vx:Math.cos(ang)*sp,vy:Math.sin(ang)*sp,life:.65+Math.random()*.7,trail:[]});
          }
        }
        if(this.ribbons.length>1200)this.ribbons=this.ribbons.slice(-900);
      }
      const rb=[];
      for(const p of this.ribbons){
        p.trail.push([p.x,p.y]);if(p.trail.length>14)p.trail.shift();
        p.x+=p.vx*60*dt;p.y+=p.vy*60*dt;p.life-=dt;
        if(p.life<=0||p.x<0||p.y<0||p.x>G||p.y>G)continue;
        // fade faster over enemy/neutral to keep silk mostly in own color (visual only)
        const gx=(p.x/S)|0,gy=(p.y/S)|0;
        if(gx>=0&&gy>=0&&gx<GS&&gy<GS){
          const own=this.grid[this.id(gx,gy)];
          if(own!==p.team)p.life-=dt*1.1;
        }
        rb.push(p);
      }
      this.ribbons=rb;
      // dense pin-dot particles (Douyin silk) — no per-dot trails for FPS
      {
        const spawnN = this.t<20?16:this.t<60?22:28;
        for(let t=0;t<4;t++){
          const [bx,by]=BASES[t],a=this.aim[t];
          for(let k=0;k<spawnN;k++){
            const ang=a+rand(-.38,.38),sp=rand(7,18);
            this.points.push(bx,by,Math.cos(ang)*sp,Math.sin(ang)*sp,.55+Math.random()*.7,t);
          }
        }
        const max=2800*6;
        if(this.points.length>max)this.points=this.points.slice(this.points.length-max);
        const out=[];
        for(let i=0;i<this.points.length;i+=6){
          let x=this.points[i],y=this.points[i+1],vx=this.points[i+2],vy=this.points[i+3],life=this.points[i+4],tm=this.points[i+5];
          x+=vx*60*dt;y+=vy*60*dt;life-=dt;
          if(life<=0||x<-10||y<-10||x>G+10||y>G+10)continue;
          if((i&15)===0){
            const gx=(x/S)|0,gy=(y/S)|0;
            if(gx>=0&&gy>=0&&gx<GS&&gy<GS){
              const own=this.grid[this.id(gx,gy)];
              if(own!==tm){life-=dt*1.8;if(Math.random()<.015)this.sparks.push({x,y,team:tm,life:.3})}
            }
          }
          out.push(x,y,vx,vy,life,tm);
        }
        this.points=out;
      }

      const count=[0,0,0,0];for(let i=0;i<this.grid.length;i++){const v=this.grid[i];if(v<4)count[v]++}
      this.share=count.map(v=>v/(GS*GS));
      for(let t=0;t<4;t++){
        this.score[t]=Math.max(0,this.score[t]+dt*(12000+this.share[t]*60000));
        if(this.t>120)this.level[t]=Math.min(99,Math.floor((this.t-100)/70)+1);
      }
      if(this.t>=MATCH){this.winner=this.share.indexOf(Math.max(...this.share));this.over=true}
      else if(this.share.some(v=>v>.9&&this.t>160)){this.winner=this.share.indexOf(Math.max(...this.share));this.over=true}
    }
    terrain(){
      const d=this.img.data,e=this.edgeImg.data,grid=this.grid;
      for(let y=0;y<GS;y++){
        for(let x=0;x<GS;x++){
          const i=y*GS+x,o=i<<2,t=grid[i];
          let r=5,g=10,b=22,edge=0;
          if(t<4){
            const team=TEAMS[t];
            const bx=BASES[t][0]/S,by=BASES[t][1]/S;
            const dx=x-bx,dy=y-by,dist=Math.sqrt(dx*dx+dy*dy);
            let fb=0;
            if(x+1>=GS||grid[i+1]!==t){edge=1;fb+=.7}
            if(x-1<0||grid[i-1]!==t){edge=1;fb+=.7}
            if(y+1>=GS||grid[i+GS]!==t){edge=1;fb+=.7}
            if(y-1<0||grid[i-GS]!==t){edge=1;fb+=.7}
            const core=1.06-Math.min(.38,dist*0.0022);
            const hi=fb>1.2?.55:fb>0.5?.3:0;
            const k=1.18*core;
            r=(team.c[0]*(1-hi)+team.hi[0]*hi)*k;
            g=(team.c[1]*(1-hi)+team.hi[1]*hi)*k;
            b=(team.c[2]*(1-hi)+team.hi[2]*hi)*k;
            if(edge){r=team.edge[0];g=team.edge[1];b=team.edge[2]}
          }
          d[o]=r>255?255:r;d[o+1]=g>255?255:g;d[o+2]=b>255?255:b;d[o+3]=255;
          if(edge&&t<4){const team=TEAMS[t];e[o]=team.edge[0];e[o+1]=team.edge[1];e[o+2]=team.edge[2];e[o+3]=255}
          else{e[o]=e[o+1]=e[o+2]=e[o+3]=0}
        }
      }
      this.ictx.putImageData(this.img,0,0);
      this.ectx.putImageData(this.edgeImg,0,0);
      this.bbctx.clearRect(0,0,512,512);
      this.bbctx.filter='blur(10px)';
      this.bbctx.drawImage(this.edge,0,0,512,512);
      this.bbctx.filter='none';
      this.dirty=false;this.terrainAge=this.frame;
    }
    draw(c){
      c.fillStyle='#030811';c.fillRect(0,0,W,H);
      this.drawLeft(c);this.drawArena(c);this.drawMeters(c);this.drawBases(c);
      if(this.paused){
        c.fillStyle='#02050bbd';c.fillRect(0,0,W,H);
        c.fillStyle='#fff';c.font='700 48px sans-serif';c.textAlign='center';c.fillText('暂停',W/2,H/2);
      }
    }
    drawLeft(c){
      const bg=c.createLinearGradient(0,0,LEFT,0);
      bg.addColorStop(0,'#061422');bg.addColorStop(.5,'#051321');bg.addColorStop(1,'#040f1a');
      c.fillStyle=bg;c.fillRect(0,0,LEFT,H);
      c.strokeStyle='#2a4558';c.lineWidth=2;c.strokeRect(1,1,LEFT-2,H-2);
      // graph paper
      c.strokeStyle='rgba(120,180,210,.05)';c.lineWidth=1;
      for(let x=0;x<LEFT;x+=180){c.beginPath();c.moveTo(x,0);c.lineTo(x,H);c.stroke()}
      for(let y=160;y<H;y+=180){c.beginPath();c.moveTo(0,y);c.lineTo(LEFT,y);c.stroke()}
      // drop line
      c.save();c.setLineDash([8,10]);c.strokeStyle='rgba(100,190,210,.22)';c.beginPath();c.moveTo(0,48);c.lineTo(LEFT,48);c.stroke();c.restore();
      for(const [px,py] of this.pegs)this.peg(c,px,py);
      for(const [px,py] of this.lowerPegs)this.peg(c,px,py);
      // central glow + arrows
      const glow=c.createRadialGradient(LEFT/2,BAND+40,6,LEFT/2,BAND+40,200);
      glow.addColorStop(0,'rgba(40,210,230,.22)');glow.addColorStop(.5,'rgba(20,100,140,.08)');glow.addColorStop(1,'rgba(0,0,0,0)');
      c.fillStyle=glow;c.fillRect(0,BAND-40,LEFT,200);
      c.strokeStyle='rgba(80,220,235,.35)';c.lineWidth=1.5;
      for(let x=240;x<520;x+=55){
        c.beginPath();c.moveTo(x,BAND+78);c.lineTo(x,BAND+28);c.lineTo(x-5,BAND+38);
        c.moveTo(x,BAND+28);c.lineTo(x+5,BAND+38);c.stroke();
      }
      // multiplier cups — taller outer, shorter inner (ref style)
      const sw=PW/6;
      for(let i=0;i<6;i++){
        const x=PX+i*sw;
        const drop=i%3===0?38:i%3===1?24:10;
        const top=BAND-8-drop;
        c.beginPath();
        c.moveTo(x+4,top);c.lineTo(x+sw-4,top+8);c.lineTo(x+sw-4,BAND+82);c.lineTo(x+4,BAND+82);
        c.closePath();
        c.fillStyle='rgba(3,12,26,.88)';c.fill();
        c.strokeStyle='rgba(170,220,245,.65)';c.lineWidth=1.6;c.stroke();
        // inner highlight
        c.strokeStyle='rgba(100,200,230,.18)';c.lineWidth=1;
        c.beginPath();c.moveTo(x+8,top+10);c.lineTo(x+8,BAND+76);c.stroke();
        c.fillStyle='#eef8ff';c.font='800 22px Arial,sans-serif';c.textAlign='center';
        c.shadowColor='rgba(120,220,255,.45)';c.shadowBlur=8;
        c.fillText('X'+MULT[i],x+sw/2,BAND+44);
        c.shadowBlur=0;
        c.font='700 14px Arial,sans-serif';c.fillStyle='#cfe8f8';
        c.fillText(''+this.hit[i],x+sw/2,BAND+68);
      }
      // marbles with trails
      for(const m of this.marbles){
        const team=TEAMS[m.team],r=m.r;
        if(m.trail.length>1){
          c.save();c.globalCompositeOperation='lighter';c.lineWidth=Math.max(2,r*.45);
          c.strokeStyle=rgb(team.glow,.35);c.beginPath();
          for(let j=0;j<m.trail.length;j++){const [tx,ty]=m.trail[j];j?c.lineTo(tx,ty):c.moveTo(tx,ty)}
          c.stroke();c.restore();
        }
        c.save();c.globalCompositeOperation='lighter';
        c.drawImage(SPR.team[m.team],m.x-r*2.2,m.y-r*2.2,r*4.4,r*4.4);
        c.restore();
        const gr=c.createRadialGradient(m.x-r*.3,m.y-r*.4,1,m.x,m.y,r);
        gr.addColorStop(0,'#fff');gr.addColorStop(.2,rgb(team.hi));gr.addColorStop(1,rgb(team.c));
        c.fillStyle=gr;c.beginPath();c.arc(m.x,m.y,r,0,Math.PI*2);c.fill();
        c.strokeStyle='rgba(255,255,255,.8)';c.lineWidth=1.3;c.stroke();
        c.fillStyle='#fff';c.textAlign='center';c.font=`800 ${r>15?12:r>11?10:8}px Arial,sans-serif`;
        c.fillText(fmt(m.v),m.x,m.y+3.5);
      }
      // item bar
      const iw=LEFT/5;
      const icons=['✧','枪','盾','●','⊕'];
      for(let i=0;i<5;i++){
        const x=i*iw+6,w=iw-12;
        const active=this.items[i]>0;
        rr(c,x,ITEMY,w,ITEMH,6,active?'rgba(8,28,48,.92)':'rgba(4,12,24,.88)',active?'rgba(120,210,255,.75)':'rgba(140,190,220,.45)',1.5);
        if(active){
          c.save();c.shadowColor='rgba(80,200,255,.4)';c.shadowBlur=12;
          c.strokeStyle='rgba(100,210,255,.35)';c.strokeRect(x+2,ITEMY+2,w-4,ITEMH-4);c.restore();
        }
        c.fillStyle=active?'#d8f4ff':'#9eb8cc';c.textAlign='center';
        c.font='22px sans-serif';c.fillText(icons[i],x+w/2,ITEMY+48);
        c.font='700 15px "Microsoft YaHei",sans-serif';c.fillText(NAMES[i],x+w/2,ITEMY+78);
        c.strokeStyle='rgba(140,190,220,.2)';c.beginPath();c.moveTo(x+14,ITEMY+92);c.lineTo(x+w-14,ITEMY+92);c.stroke();
        c.fillStyle='#f0faff';c.font='800 18px Arial';c.fillText(''+this.items[i],x+w/2,ITEMY+118);
      }
      c.strokeStyle='#243848';c.beginPath();c.moveTo(LEFT-1,0);c.lineTo(LEFT-1,H);c.stroke();
    }
    peg(c,x,y){
      const g=c.createRadialGradient(x-1.2,y-1.2,.5,x,y,5.5);
      g.addColorStop(0,'#fff');g.addColorStop(.45,'#c5d0dc');g.addColorStop(1,'rgba(120,150,175,.35)');
      c.fillStyle=g;c.beginPath();c.arc(x,y,4.8,0,Math.PI*2);c.fill();
    }
    drawArena(c){
      c.fillStyle='#02080f';c.fillRect(AX-4,AY-4,G+8,G+8);
      // stars
      for(const [x,y,a,s] of this.stars){
        const tw=.4+.6*Math.sin(this.t*1.4+x*.08);
        c.fillStyle=`rgba(190,220,255,${a*tw*.7})`;
        c.beginPath();c.arc(AX+x,AY+y,s,0,Math.PI*2);c.fill();
      }
      // throttle terrain rebuild
      if(this.dirty&&(this.terrainAge===0||this.frame-this.terrainAge>=8))this.terrain();
      c.save();c.imageSmoothingEnabled=true;
      // soft nebula fill (slight blur upscale) then crisp pass
      c.filter='blur(1.1px)';c.globalAlpha=.92;c.drawImage(this.image,AX,AY,G,G);
      c.filter='none';c.globalAlpha=.55;c.drawImage(this.image,AX,AY,G,G);
      c.globalAlpha=1;c.restore();
      // faint 100px grid
      c.save();c.strokeStyle='rgba(140,175,210,.08)';c.lineWidth=1;
      for(let i=0;i<=10;i++){
        const q=AX+i*100;c.beginPath();c.moveTo(q,AY);c.lineTo(q,AY+G);c.stroke();
        const q2=AY+i*100;c.beginPath();c.moveTo(AX,q2);c.lineTo(AX+G,q2);c.stroke();
      }
      c.restore();
      // neon frontier bloom layers (softer)
      c.save();c.globalCompositeOperation='lighter';
      c.globalAlpha=.7;c.drawImage(this.bloomBig,AX,AY,G,G);
      c.globalAlpha=.45;c.drawImage(this.edge,AX-1,AY-1,G+2,G+2);
      c.globalAlpha=.55;c.drawImage(this.edge,AX,AY,G,G);
      c.restore();
      // bullets — dense additive streams
      c.save();c.globalCompositeOperation='lighter';
      const age=this.t/MATCH;
      for(const p of this.shots){
        const team=TEAMS[p.team],len=p.trail.length;
        const x=AX+p.x,y=AY+p.y;
        if(len>1){
          c.beginPath();
          for(let j=0;j<len;j++){const [tx,ty]=p.trail[j];j?c.lineTo(AX+tx,AY+ty):c.moveTo(AX+tx,AY+ty)}
          if(p.kind===2){c.strokeStyle=rgb(team.hi,.55);c.lineWidth=4.5;c.stroke()}
          else if(p.kind===3){c.strokeStyle=rgb(team.glow,.5);c.lineWidth=2.2;c.stroke()}
          else if(age>.45||p.kind===4){c.strokeStyle=rgb(team.hi,.28);c.lineWidth=1.1;c.stroke()}
          else{c.strokeStyle='rgba(255,255,255,.22)';c.lineWidth=1.4;c.stroke()}
        }
        if(p.kind===2){
          const r=clamp(18+Math.sqrt(p.value/1e6)*5,28,110);
          c.drawImage(SPR.team[p.team],x-r*1.6,y-r*1.6,r*3.2,r*3.2);
          const grad=c.createRadialGradient(x-r*.3,y-r*.35,2,x,y,r);
          grad.addColorStop(0,'rgba(255,255,255,.75)');
          grad.addColorStop(.12,rgb(team.hi,.95));
          grad.addColorStop(.55,rgb(team.c,.55));
          grad.addColorStop(1,rgb(team.c,.05));
          c.fillStyle=grad;c.beginPath();c.arc(x,y,r,0,Math.PI*2);c.fill();
          c.strokeStyle=rgb(team.hi,.95);c.lineWidth=3.5;c.stroke();
          c.globalCompositeOperation='source-over';
          c.fillStyle='#fff';c.textAlign='center';c.font='900 22px Arial,sans-serif';
          c.fillText(fmt(p.value),x,y+7);
          c.globalCompositeOperation='lighter';
        }else{
          const sz=p.kind===3?10:age>.5?7:8;
          c.drawImage(SPR.whiteSoft,x-sz,y-sz,sz*2,sz*2);
          c.drawImage(SPR.whiteCore,x-3,y-3,6,6);
        }
      }
      c.restore();
      // dense pin dots
      c.save();c.globalCompositeOperation='lighter';
      const pts=this.points;
      c.fillStyle='#ffffff';
      for(let i=0;i<pts.length;i+=6){
        const life=pts[i+4];
        if(life<.08)continue;
        c.globalAlpha=Math.min(1,life*2);
        c.fillRect(AX+pts[i]-1.1,AY+pts[i+1]-1.1,2.2,2.2);
      }
      c.globalAlpha=1;c.restore();
      // silk ribbons — dense white/neon hairlines like Douyin mid-game
      c.save();c.globalCompositeOperation='lighter';
      for(const p of this.ribbons){
        const team=TEAMS[p.team],len=p.trail.length;
        const alpha=Math.min(1,p.life*1.8);
        if(len>1){
          c.beginPath();
          for(let j=0;j<len;j++){const [tx,ty]=p.trail[j];j?c.lineTo(AX+tx,AY+ty):c.moveTo(AX+tx,AY+ty)}
          c.strokeStyle=`rgba(255,255,255,${.28*alpha})`;c.lineWidth=1.0;c.stroke();
        }
        const x=AX+p.x,y=AY+p.y;
        c.globalAlpha=alpha;
        c.drawImage(SPR.whiteCore,x-3,y-3,6,6);
        c.globalAlpha=1;
      }
      c.restore();
      // impact + frontier sparks
      for(const s of this.sparks){
        const x=AX+s.x,y=AY+s.y,team=TEAMS[s.team];
        if(s.burst){
          c.save();c.globalAlpha=s.life*.55;c.strokeStyle=rgb(team.hi);c.lineWidth=2.5;
          c.beginPath();c.arc(x,y,(1-s.life)*160+40,0,Math.PI*2);c.stroke();c.restore();continue;
        }
        c.save();c.globalCompositeOperation='lighter';c.globalAlpha=s.life;
        c.drawImage(SPR.spark,x-8,y-8,16,16);
        c.strokeStyle=rgb(team.hi);c.lineWidth=1.2;
        for(let k=0;k<5;k++){
          const a=k*Math.PI*2/5+s.x*.05,dist=6+12*s.life;
          c.beginPath();c.moveTo(x,y);c.lineTo(x+Math.cos(a)*dist,y+Math.sin(a)*dist);c.stroke();
        }
        c.restore();
      }
      for(const s of this.frontierSparks){
        const x=AX+s.x,y=AY+s.y;
        c.save();c.globalCompositeOperation='lighter';c.globalAlpha=s.life*.9;
        c.drawImage(SPR.spark,x-5,y-5,10,10);c.restore();
      }
      c.strokeStyle='rgba(90,140,180,.55)';c.lineWidth=1.4;c.strokeRect(AX+.5,AY+.5,G-1,G-1);
    }
    drawBases(c){
      const corner=[[.12,.12],[.88,.12],[.12,.88],[.88,.88]];
      for(let t=0;t<4;t++){
        const team=TEAMS[t],[ux,uy]=corner[t];
        const x=AX+G*ux,y=AY+G*uy;
        const r=clamp(42+Math.sqrt(this.share[t])*160,44,108);
        const pulse=Math.sin(this.t*2.4+t)*2.8;
        // outer halo
        c.save();c.globalCompositeOperation='lighter';
        c.drawImage(SPR.team[t],x-r*2.1,y-r*2.1,r*4.2,r*4.2);
        c.restore();
        // rings
        c.save();
        c.shadowColor=rgb(team.glow);c.shadowBlur=28;
        c.strokeStyle=rgb(team.glow,.95);c.lineWidth=3.2;
        c.beginPath();c.arc(x,y,r+pulse,0,Math.PI*2);c.stroke();
        c.shadowBlur=16;c.strokeStyle=rgb(team.hi,.7);c.lineWidth=6;
        c.beginPath();c.arc(x,y,r-8,0,Math.PI*2);c.stroke();
        c.restore();
        // inner disc
        const fill=c.createRadialGradient(x-r*.25,y-r*.35,2,x,y,r);
        fill.addColorStop(0,rgb(team.hi,.22));
        fill.addColorStop(.55,'rgba(2,8,18,.72)');
        fill.addColorStop(1,'rgba(1,5,12,.88)');
        c.fillStyle=fill;c.beginPath();c.arc(x,y,r-6,0,Math.PI*2);c.fill();
        // shield icon
        c.fillStyle=rgb(team.hi);c.font=`${Math.max(14,r*.22)}px sans-serif`;c.textAlign='center';
        c.fillText('⬡',x-r*.42,y-r*.18);
        // HUGE ammo number
        c.fillStyle='#ffffff';c.textAlign='left';
        const ammoFs=clamp(r*.42,22,40);
        c.font=`800 ${ammoFs}px Arial,sans-serif`;
        c.shadowColor=rgb(team.glow);c.shadowBlur=10;
        c.fillText(fmt(this.ammo[t]),x-r*.22,y-r*.12);
        c.shadowBlur=0;
        // secondary score panel
        const pw=r*1.35,ph=Math.max(22,r*.32);
        rr(c,x-pw/2,y+r*.02,pw,ph,5,'rgba(2,8,18,.75)','rgba(200,230,250,.22)',1);
        const secondary=Math.max(1000, Math.round(this.score[t]*0.045 + this.share[t]*180000));
        c.fillStyle='#dcecff';c.font=`700 ${Math.max(13,r*.24)}px Arial`;c.textAlign='center';
        c.fillText(fmtScore(secondary),x,y+r*.02+ph*.72);
        // center pip + aim
        c.fillStyle='rgba(5,12,22,.85)';c.beginPath();c.arc(x,y,6,0,Math.PI*2);c.fill();
        c.fillStyle=rgb(team.hi);c.beginPath();c.arc(x,y,3.5,0,Math.PI*2);c.fill();
        const a=this.aim[t];
        c.strokeStyle=rgb(team.glow,.9);c.lineWidth=3.5;
        c.beginPath();c.moveTo(x,y);c.lineTo(x+Math.cos(a)*(r*.58),y+Math.sin(a)*(r*.58));c.stroke();
      }
    }
    drawMeters(c){
      const one=(x,t,y0)=>{
        const team=TEAMS[t],h=458,share=this.share[t],y=y0+h;
        c.save();
        c.fillStyle='rgba(4,12,22,.9)';c.fillRect(x-14,y0-6,38,h+12);
        c.fillStyle='rgba(100,140,170,.12)';c.fillRect(x,y0,3,h);
        c.save();c.shadowColor=rgb(team.glow);c.shadowBlur=12;
        c.fillStyle=rgb(team.glow,.88);c.fillRect(x,y0,3,h);c.restore();
        for(let q=0;q<=4;q++){
          const yy=y0+h*q/4;
          c.strokeStyle='rgba(150,195,220,.55)';c.lineWidth=1;
          c.beginPath();c.moveTo(x-6,yy);c.lineTo(x+10,yy);c.stroke();
          c.fillStyle='#a8c0d4';c.font='10px Arial';c.textAlign=x<1100?'right':'left';
          c.fillText((100-q*25)+'%',x<1100?x-9:x+12,yy+3);
        }
        const mark=y-share*h;
        c.save();c.shadowColor=rgb(team.glow);c.shadowBlur=14;
        c.fillStyle=rgb(team.hi);c.fillRect(x-3,mark-3,9,6);c.restore();
        c.fillStyle=rgb(team.hi);c.font='800 17px Arial';c.textAlign=x<1100?'right':'left';
        c.fillText((share*100).toFixed(2)+'%',x<1100?x+10:x-10,y0<500?y0-10:y0+h+32);
        const badgeY=y0<500?y0+100:y0+355;
        c.save();c.shadowColor=rgb(team.glow);c.shadowBlur=14;
        c.strokeStyle=rgb(team.glow);c.lineWidth=2.4;c.beginPath();c.arc(x+1.5,badgeY,20,0,Math.PI*2);c.stroke();c.restore();
        c.fillStyle='#061018';c.beginPath();c.arc(x+1.5,badgeY,14,0,Math.PI*2);c.fill();
        c.fillStyle='#fff';c.textAlign='center';c.font='800 14px Arial';c.fillText(''+this.level[t],x+1.5,badgeY+5);
        c.restore();
      };
      one(812,0,40);one(812,2,582);one(1894,1,40);one(1894,3,582);
    }
  }

  let game=null,preview=null,playing=false,raf=0,last=0;
  function showStart(){
    overlay.classList.remove('hidden');
    startpanel.classList.remove('hidden');
    endpanel.classList.add('hidden');
    overlay.style.display='grid';
    document.getElementById('shareLabel').textContent='等待开战';
    document.getElementById('timer').textContent='00:00';
  }
  function fit(){const r=Math.min(innerWidth/W,innerHeight/H);canvas.style.width=(W*r)+'px';canvas.style.height=(H*r)+'px'}
  addEventListener('resize',fit);fit();
  function pos(e){const r=canvas.getBoundingClientRect();return{x:(e.clientX-r.left)*W/r.width,y:(e.clientY-r.top)*H/r.height}}
  function aimAt(p){if(!game||!playing)return;const [bx,by]=BASES[game.player];game.playerAim=Math.atan2(p.y-(AY+by),p.x-(AX+bx))}
  canvas.addEventListener('pointerdown',e=>{
    if(!playing||!game||game.over)return;
    canvas.setPointerCapture(e.pointerId);
    const p=pos(e);
    if(p.x<LEFT&&p.y>ITEMY&&p.y<ITEMY+ITEMH){const i=clamp(Math.floor(p.x/(LEFT/5)),0,4);game.use(game.player,i);return}
    if(p.x>=AX&&p.x<=AX+G&&p.y>=AY&&p.y<=AY+G){if(!game.autoAim)aimAt(p);game.firing=true}
  });
  canvas.addEventListener('pointermove',e=>{if(game&&playing&&!game.autoAim)aimAt(pos(e))});
  canvas.addEventListener('pointerup',()=>{if(game)game.firing=false});
  canvas.addEventListener('pointercancel',()=>{if(game)game.firing=false});
  document.getElementById('autoAim').addEventListener('change',e=>{if(game)game.autoAim=e.target.checked});
  document.getElementById('btnPause').addEventListener('click',()=>{if(game&&playing)game.paused=!game.paused});
  document.getElementById('btnRestart').addEventListener('click',()=>{if(playing&&game)start(game.player);else showStart()});
  document.getElementById('btnAgain').addEventListener('click',()=>{playing=false;showStart()});
  document.querySelectorAll('.color-btn').forEach(b=>b.addEventListener('click',ev=>{ev.preventDefault();ev.stopPropagation();start(+b.dataset.team)}));
  const quick=document.getElementById('btnQuick');
  if(quick)quick.addEventListener('click',()=>start(0));
  addEventListener('keydown',e=>{
    if(!playing){if(e.key>='1'&&e.key<='4'){start(+e.key-1);e.preventDefault()}return}
    if(!game)return;
    if(e.key===' '){game.paused=!game.paused;e.preventDefault()}
    const n=+e.key;if(n>=1&&n<=5)game.use(game.player,n-1);
  });
  function start(t){
    t=((t|0)%4+4)%4;
    playing=true;
    overlay.classList.remove('shown');
    game=new Game(t);
    preview=null;
    game.autoAim=document.getElementById('autoAim').checked;
    game.playerAim=game.aim[t];
    overlay.classList.add('hidden');
    startpanel.classList.add('hidden');
    endpanel.classList.add('hidden');
    last=performance.now();
    document.getElementById('timer').textContent='00:00';
    document.getElementById('shareLabel').textContent=TEAMS[t].name+' 0.0%';
  }
  function sync(){
    if(!game||!playing)return;
    const elapsed=Math.max(0,Math.floor(game.t|0));
    const m=Math.floor(elapsed/60),s=elapsed%60;
    document.getElementById('timer').textContent=String(m).padStart(2,'0')+':'+String(s).padStart(2,'0');
    document.getElementById('shareLabel').textContent=TEAMS[game.player].name+' '+(game.share[game.player]*100).toFixed(1)+'%';
  }
  function finish(){
    playing=false;
    overlay.classList.remove('hidden');
    overlay.style.display='grid';
    startpanel.classList.add('hidden');
    endpanel.classList.remove('hidden');
    document.getElementById('endMsg').textContent=`${TEAMS[game.winner].name} 获胜 · 占领 ${(game.share[game.winner]*100).toFixed(1)}%`;
  }
  function ensurePreview(){
    if(!preview){preview=new Game(0);preview.autoFire=false;preview.paused=true}
    return preview;
  }
  function loop(now){
    raf=requestAnimationFrame(loop);
    const dt=Math.min(.05,Math.max(0,(now-last)/1000));last=now;
    if(playing&&game){
      window.__W4B=game;game.tick(dt);game.draw(ctx);sync();
      if(game.over&&!overlay.classList.contains('shown')){finish();overlay.classList.add('shown')}
    }else{
      if(overlay.classList.contains('hidden'))showStart();
      const p=ensurePreview();
      p.paused=false;p.autoFire=true;p.tick(Math.min(dt,.033));p.paused=true;p.draw(ctx);
    }
  }
  showStart();
  loop(performance.now());
})();
